#!/usr/bin/env python3
"""
Apollo Pharmacy Composition API

Dependencies:
    pip install flask selenium webdriver-manager

Usage:
    python api_server.py
    The API will listen on http://0.0.0.0:5000

Example:
    GET /search?drug-name=bilypsa%204mg%20tablet
    => JSON {"drugName":"...","saltComposition":"..."}
"""

import re
import json
import time
from difflib import SequenceMatcher
from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

app = Flask(__name__)


def clean_input(name: str) -> str:
    name = name.lower()
    name = re.sub(r'[^a-z0-9\s]', ' ', name)
    form_words = [
        r'\btablet(?:s)?\b', r'\btabs?\b',
        r'\bcapsule(?:s)?\b', r'\bcap\b', r'\bstrip\b',
        r'\bsyrup\b', r'\binjection\b', r'\bointment\b',
        r'\bcream\b', r'\bsolution\b', r'\bdrop(?:s)?\b'
    ]
    for fw in form_words:
        name = re.sub(fw, ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    name = re.sub(r'(\d+)\s*mg', r'\1mg', name)
    return name


def get_best_match_link(driver, cleaned_query: str):
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, '//a[contains(@href,"/otc/") or contains(@href,"/medicine/")]'))
    )
    elems = driver.find_elements(By.XPATH, '//a[contains(@href,"/otc/") or contains(@href,"/medicine/")]')
    candidates = []
    flat_query = cleaned_query.replace(' ', '')
    for a in elems:
        txt = a.text.strip()
        if not txt:
            continue
        cleaned_title = clean_input(txt).replace(' ', '')
        candidates.append((cleaned_title, a.get_attribute('href'), a))
    if not candidates:
        return None
    subset = [c for c in candidates if flat_query in c[0] or c[0] in flat_query]
    pool = subset if subset else candidates
    best = max(pool, key=lambda c: SequenceMatcher(None, flat_query, c[0]).ratio())
    return best[2]


def extract_composition(driver):
    try:
        heading = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//h3[contains(text(),"Composition")]'))
        )
        block = heading.find_element(By.XPATH, 'following-sibling::*[1]')
        text = block.text.strip()
        if text:
            return text
    except:
        pass
    try:
        comp_div = driver.find_element(By.ID, 'composition')
        paragraphs = comp_div.find_elements(By.TAG_NAME, 'p')
        text = ' '.join(p.text for p in paragraphs if p.text)
        if text:
            return text.strip()
    except:
        pass
    try:
        block = driver.find_element(By.XPATH, '//div[contains(@class,"compositionWrapper")]')
        return block.text.strip()
    except:
        return ''


def scrape_composition(drug_name: str) -> dict:
    cleaned = clean_input(drug_name)
    url = f"https://www.apollopharmacy.in/search-medicines/{cleaned.replace(' ', '%20')}"

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--log-level=3")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    try:
        driver.get(url)
        time.sleep(2)

        best_elem = get_best_match_link(driver, cleaned)
        if not best_elem:
            return {"drugName": drug_name, "saltComposition": ""}

        href = best_elem.get_attribute("href")
        driver.get(href)
        time.sleep(2)

        try:
            title_el = driver.find_element(By.XPATH, '//*[contains(@class,"DrugHeader__header-content")]')
            title = title_el.text.strip()
        except:
            title = drug_name

        comp = extract_composition(driver)
        return {"drugName": title, "saltComposition": comp}
    finally:
        driver.quit()


@app.route('/search', methods=['GET'])
def api_search():
    drug_name = request.args.get('drug-name', '')
    if not drug_name:
        return jsonify({"error": "Please provide 'drug-name' parameter"}), 400

    result = scrape_composition(drug_name)
    return jsonify(result)


if __name__ == '__main__':
    # listen on all interfaces, port 5000
    app.run(host='0.0.0.0', port=5000)
