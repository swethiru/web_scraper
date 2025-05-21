#!/usr/bin/env python3
"""
Apollo Pharmacy Composition API

Dependencies:
    pip install flask selenium webdriver-manager

Usage:
    python Apollo.py
    The API will listen on http://0.0.0.0:5000

Example:
    GET /search?drug-name=bilypsa%204mg%20tablet
    => JSON {"drugName":"...","saltComposition":"..."}
"""

import re
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
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


def clean_input(name: str) -> str:
    name = name.lower()
    name = re.sub(r'[^a-z0-9\s]', ' ', name)
    for fw in [r'\btablet(?:s)?\b', r'\btabs?\b', r'\bcapsule(?:s)?\b',
               r'\bcap\b', r'\bstrip\b', r'\bsyrup\b', r'\binjection\b',
               r'\bointment\b', r'\bcream\b', r'\bsolution\b', r'\bdrop(?:s)?\b']:
        name = re.sub(fw, ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    name = re.sub(r'(\d+)\s*mg', r'\1mg', name)
    return name

def get_best_match_link(driver, cleaned_query: str):
    # 1) Try waiting briefly for any product link to appear
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((
                By.XPATH,
                '//a[contains(@href,"/otc/") or contains(@href,"/medicine/")]'
            ))
        )
    except TimeoutException:
        logger.info("Timeout waiting for product links—falling back to scraping whatever is present.")

    # 2) Grab all matching links whether or not the wait succeeded
    elems = driver.find_elements(
        By.XPATH,
        '//a[contains(@href,"/otc/") or contains(@href,"/medicine/")]'
    )

    # 3) If none found, give up
    if not elems:
        return None

    # 4) Build candidates list and pick best match
    flat_query = cleaned_query.replace(' ', '')
    candidates = []
    for a in elems:
        txt = a.text.strip()
        if not txt:
            continue
        cleaned_title = clean_input(txt).replace(' ', '')
        candidates.append((cleaned_title, a.get_attribute('href'), a))

    subset = [c for c in candidates if flat_query in c[0] or c[0] in flat_query]
    pool = subset if subset else candidates
    return max(pool, key=lambda c: SequenceMatcher(None, flat_query, c[0]).ratio())[2]

def extract_composition(driver):
    # 1) Wait a moment and look for the exact h3 classes you shared
    try:
        time.sleep(2)
        heading = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h3.Gd.Dd.Sp"))
        )
        block = heading.find_element(By.XPATH, "following-sibling::*[1]")
        if block.text.strip():
            return block.text.strip()
    except Exception:
        pass

    # 2) Fallback: any h3 containing "Composition"
    try:
        heading = driver.find_element(
            By.XPATH, "//h3[contains(., 'Composition')]"
        )
        block = heading.find_element(By.XPATH, "following-sibling::*[1]")
        if block.text.strip():
            return block.text.strip()
    except NoSuchElementException:
        pass

    # 3) Fallback: #composition div paragraphs
    try:
        comp_div = driver.find_element(By.ID, "composition")
        paras = comp_div.find_elements(By.TAG_NAME, "p")
        joined = " ".join(p.text for p in paras if p.text)
        if joined:
            return joined
    except NoSuchElementException:
        pass

    # 4) Final fallback: any wrapper
    try:
        wrapper = driver.find_element(
            By.XPATH, "//div[contains(@class,'compositionWrapper')]"
        )
        return wrapper.text.strip()
    except NoSuchElementException:
        return ""


def scrape_composition(drug_name: str) -> dict:
    cleaned = clean_input(drug_name)
    search_url = f"https://www.apollopharmacy.in/search-medicines/{cleaned.replace(' ', '%20')}"

    options = Options()
    options.add_argument("--headless")           # classic headless mode
    options.add_argument("--no-sandbox")         # required for many Linux containers
    options.add_argument("--disable-dev-shm-usage")  # avoid /dev/shm issues
    options.add_argument("--disable-gpu")        # disable GPU for headless
    options.add_argument("--log-level=3")        # suppress most logging


    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    try:
        driver.get(search_url)
        time.sleep(2)
        # Wait for any medicine link to appear
        try:
            WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((
                By.XPATH,
                '//a[contains(@href,"/otc/") or contains(@href,"/medicine/")]'
            ))
        )
        except TimeoutException:
            logger.info("Timeout waiting for product links—falling back to scrape whatever is present.")

        best_elem = get_best_match_link(driver, cleaned)
        if not best_elem:
            return {"drugName": drug_name, "saltComposition": ""}

        driver.get(best_elem.get_attribute("href"))
        comp = extract_composition(driver)

        # get title if possible
        try:
            title_el = driver.find_element(
                By.XPATH, '//*[contains(@class,"DrugHeader__header-content")]'
            )
            title = title_el.text.strip()
        except NoSuchElementException:
            title = drug_name

        return {"drugName": title, "saltComposition": comp}

    finally:
        driver.quit()


@app.route('/search', methods=['GET'])
def api_search():
    name = request.args.get("drug-name", "").strip()
    if not name:
        return jsonify({"error": "Please provide 'drug-name' parameter"}), 400

    try:
        result = scrape_composition(name)
        return jsonify(result)
    except Exception:
        logger.exception("Unexpected error in /search")
        return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)













