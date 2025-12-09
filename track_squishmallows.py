import os
import re
import json
import smtplib
from email.mime.text import MIMEText
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# -------------- CONFIG --------------

SEARCH_URL = "https://www.frysfood.com/q/squishmallow"
STATE_FILE = "last_prices.json"

# what you consider "small" – tweak as needed
SMALL_SIZES = ["2.5 in", "4 in", "5 in", "6 in", "7 in", "8 in"]

EMAIL_USER = os.environ.get("EMAIL_USER")   # sender email
EMAIL_PASS = os.environ.get("EMAIL_PASS")   # app password
ALERT_TO   = os.environ.get("ALERT_TO")     # phone SMS email

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# -------------- HELPERS --------------

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def send_alert(changed_items):
    if not changed_items or not (EMAIL_USER and EMAIL_PASS and ALERT_TO):
        return

    lines = []
    for item in changed_items:
        lines.append(
            f"{item['name']} ({item['size']})\n"
            f"Old price: {item['old_price']}\n"
            f"New price: {item['price']}\n"
            f"Link: {item['url']}\n"
        )
    body = "\n---\n".join(lines)

    msg = MIMEText(body)
    msg["Subject"] = f"[Fry's] Squishmallow price changes ({len(changed_items)} item(s))"
    msg["From"] = EMAIL_USER
    msg["To"] = ALERT_TO

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)

def parse_price(text):
    m = re.search(r"\$([\d]+\.\d{2})", text)
    return float(m.group(1)) if m else None

def is_small_size(text):
    for size in SMALL_SIZES:
        if size in text:
            return size
    return None

def scrape_items():
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; PriceTrackerBot/1.0)"
    }
    r = requests.get(SEARCH_URL, headers=headers, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    items = []
    product_cards = soup.select('[data-qa="product-card"], div.ProductCard, li') or soup.find_all("li")

    seen = set()

    for card in product_cards:
        text = card.get_text(" ", strip=True)
        if "Squishmallow" not in text and "Squishmallows" not in text:
            continue

        name_el = card.select_one('[data-qa="product-name"]')
        if name_el:
            name = name_el.get_text(strip=True)
        else:
            name = None
            for tag in card.find_all(["h2", "h3", "h4", "strong", "a"]):
                txt = tag.get_text(strip=True)
                if "Squish" in txt:
                    name = txt
                    break
            if not name:
                name = text[:80]

        size = is_small_size(text)
        if not size:
            continue

        price_el = card.select_one('[data-qa="product-price"], [class*=\"Price\"]')
        price_text = price_el.get_text(" ", strip=True) if price_el else text
        price = parse_price(price_text)
        if price is None:
            continue

        link_el = card.find("a", href=True)
        if link_el:
            url = urljoin(SEARCH_URL, link_el["href"])
        else:
            url = SEARCH_URL

        key = url
        if key in seen:
            continue
        seen.add(key)

        items.append({
            "key": key,
            "name": name,
            "size": size,
            "price": price,
            "url": url,
        })

    return items

def main():
    old_state = load_state()
    current_items = scrape_items()

    new_state = {}
    changed = []

    for item in current_items:
        key = item["key"]
        price = item["price"]
        new_state[key] = {
            "name": item["name"],
            "size": item["size"],
            "price": price,
            "url": item["url"],
        }

        if key in old_state:
            old_price = old_state[key]["price"]
            if price != old_price:
                changed.append({
                    "name": item["name"],
                    "size": item["size"],
                    "url": item["url"],
                    "old_price": old_price,
                    "price": price,
                })

    # First run: only save, don't spam you with "changes from nothing"
    if old_state and changed:
        send_alert(changed)

    save_state(new_state)

if __name__ == "__main__":
    main()
