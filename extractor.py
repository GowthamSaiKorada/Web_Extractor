import re
import json
import sqlite3
import datetime
import requests
import time
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from typing import Dict, Optional, Tuple, Any
from dotenv import load_dotenv
import os

# Load environment variables (Gemini API key, etc.)
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ---------- Regex patterns ----------
CURRENCY_RE = re.compile(r'(\$|€|£|\u20B9)\s?[\d,]+(\.\d+)?')
NUMBER_RE = re.compile(r'[\d,]+(\.\d+)?')

# ---------- Fetch HTML ----------
def fetch_html(url: str, timeout=20, headers=None, retries=3, backoff=2) -> Tuple[str, str]:
    """
    Fetch a webpage’s HTML with retries, custom headers, and timeout.
    """
    headers = headers or {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    }

    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=timeout, headers=headers)
            r.raise_for_status()
            return r.url, r.text
        except requests.exceptions.RequestException as e:
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
                continue
            raise e


# ---------- Snapshot Storage ----------
def snapshot_to_db(db_path: str, url: str, html: str):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT,
            domain TEXT,
            fetched_at TEXT,
            html TEXT
        )
    """)
    domain = urlparse(url).netloc
    cur.execute(
        "INSERT INTO snapshots (url, domain, fetched_at, html) VALUES (?, ?, ?, ?)",
        (url, domain, datetime.datetime.utcnow().isoformat(), html)
    )
    conn.commit()
    conn.close()


# ---------- Heuristic Extraction ----------
def infer_title(soup: BeautifulSoup) -> Optional[str]:
    tag = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "twitter:title"})
    if tag and tag.get("content"):
        return tag["content"].strip()
    if soup.title and soup.title.text.strip():
        return soup.title.text.strip()
    for tag_name in ["h1", "h2", "h3"]:
        tag = soup.find(tag_name)
        if tag and tag.text.strip():
            return tag.text.strip()
    return None


def infer_price(soup: BeautifulSoup) -> Optional[str]:
    def has_price_keyword(s):
        return any(k in s.lower() for k in ["price", "amount", "cost", "sale", "our-price", "discount"])

    for tag in soup.find_all(True, attrs={"class": True}):
        cls = " ".join(tag.get("class"))
        if has_price_keyword(cls):
            text = tag.get_text(" ", strip=True)
            if CURRENCY_RE.search(text):
                return CURRENCY_RE.search(text).group(0)
    for tag in soup.find_all(True, attrs={"id": True}):
        ident = tag.get("id")
        if has_price_keyword(ident):
            text = tag.get_text(" ", strip=True)
            if CURRENCY_RE.search(text):
                return CURRENCY_RE.search(text).group(0)
    text = soup.get_text(" ", strip=True)
    m = CURRENCY_RE.search(text)
    if m:
        return m.group(0)
    return None


def infer_availability(soup: BeautifulSoup) -> Optional[str]:
    text = soup.get_text(" ", strip=True).lower()
    for phrase in ["in stock", "out of stock", "available", "pre-order", "coming soon"]:
        if phrase in text:
            idx = text.find(phrase)
            return text[max(0, idx - 30): idx + 50].strip()
    return None


def infer_specs(soup: BeautifulSoup) -> Dict[str, str]:
    specs = {}

    # From tables
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for r in rows:
            cells = r.find_all(["td", "th"])
            if len(cells) == 2:
                key = cells[0].get_text(" ", strip=True)
                val = cells[1].get_text(" ", strip=True)
                if key and val:
                    specs[key] = val

    # From UL/LI
    if not specs:
        for ul in soup.find_all("ul"):
            items = [li.get_text(" ", strip=True) for li in ul.find_all("li")]
            if items and len(items) >= 2:
                specs = {f"Spec_{i+1}": v for i, v in enumerate(items[:10])}
                break
    return specs


def apply_selectors(soup: BeautifulSoup, mapping: Dict[str, str]) -> Dict[str, Optional[str]]:
    results = {}
    for field, selector in mapping.items():
        if not selector:
            results[field] = None
            continue
        try:
            tag = soup.select_one(selector)
            results[field] = tag.get_text(" ", strip=True) if tag else None
        except Exception:
            results[field] = None
    return results


def normalize_fields(raw: Dict[str, Optional[str]]) -> Dict[str, Any]:
    price_raw = raw.get("price")
    currency = None
    amount = None
    if price_raw:
        m = CURRENCY_RE.search(price_raw)
        if m:
            currency = m.group(1)
        num_m = NUMBER_RE.search(price_raw)
        if num_m:
            try:
                amount = float(num_m.group(0).replace(",", ""))
            except:
                pass
    return {
        "title": raw.get("title"),
        "price": {"raw": price_raw, "amount": amount, "currency": currency},
        "availability": raw.get("availability"),
        "specs": raw.get("specs", {}),
        "extraction_timestamp": datetime.datetime.utcnow().isoformat() + "Z"
    }


def extract_from_html(html: str, mapping: Dict[str, str] = {}) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    selected = apply_selectors(soup, mapping)

    if not selected.get("title"):
        selected["title"] = infer_title(soup)
    if not selected.get("price"):
        selected["price"] = infer_price(soup)
    if not selected.get("availability"):
        selected["availability"] = infer_availability(soup)

    selected["specs"] = infer_specs(soup)
    return normalize_fields(selected)
