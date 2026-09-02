import os
import re
import json
import time
import html
from pathlib import Path
from urllib.parse import urljoin

import requests
import xml.etree.ElementTree as ET

NTFY_TOPIC = os.environ["NTFY_TOPIC"]

# Alert thresholds in AUD
GOOD_DEAL = 650
GREAT_DEAL = 600
PRICE_ERROR = 550

STATE_FILE = Path("seen_deals.json")

FEEDS = [
    {
        "name": "OzBargain New Deals",
        "url": "https://www.ozbargain.com.au/deals/feed",
        "currency": "AUD",
    },
]

KEYWORDS = [
    "oura ring 5",
    "oura 5",
    "oura ring",
]

GOLD_WORDS = [
    "gold",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
    )
}


def load_seen():
    if not STATE_FILE.exists():
        return set()
    try:
        return set(json.loads(STATE_FILE.read_text()))
    except Exception:
        return set()


def save_seen(seen):
    STATE_FILE.write_text(json.dumps(sorted(seen)))


def clean_text(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def extract_aud_prices(text):
    prices = []

    patterns = [
        r"A\$\s*([0-9]{2,4}(?:\.[0-9]{1,2})?)",
        r"AU\$\s*([0-9]{2,4}(?:\.[0-9]{1,2})?)",
        r"\$\s*([0-9]{2,4}(?:\.[0-9]{1,2})?)",
    ]

    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.I):
            try:
                value = float(match)
                if 100 <= value <= 1500:
                    prices.append(value)
            except ValueError:
                pass

    return sorted(set(prices))


def classify(price):
    if price <= PRICE_ERROR:
        return "🚨 POSSIBLE PRICE ERROR"
    if price <= GREAT_DEAL:
        return "🔥 GREAT DEAL"
    if price <= GOOD_DEAL:
        return "💍 GOOD DEAL"
    return None


def send_ntfy(title, message, link):
    requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={
            "Title": title,
            "Priority": "high",
            "Click": link,
            "Tags": "ring,moneybag",
        },
        timeout=15,
    )


def fetch_feed(feed):
    response = requests.get(
        feed["url"],
        headers=HEADERS,
        timeout=20,
    )
    response.raise_for_status()
    return response.text


def parse_feed(xml_text):
    root = ET.fromstring(xml_text)

    items = []

    for item in root.findall(".//item"):
        title = clean_text(item.findtext("title"))
        description = clean_text(item.findtext("description"))
        link = clean_text(item.findtext("link"))
        guid = clean_text(item.findtext("guid"))

        items.append(
            {
                "title": title,
                "description": description,
                "link": link,
                "id": guid or link or title,
            }
        )

    return items


def relevant(item):
    text = f"{item['title']} {item['description']}".lower()

    has_oura = any(word in text for word in KEYWORDS)
    has_gold = any(word in text for word in GOLD_WORDS)

    return has_oura and has_gold


def main():
    seen = load_seen()

    for feed in FEEDS:
        try:
            xml_text = fetch_feed(feed)
            items = parse_feed(xml_text)

        except Exception as exc:
            print(f"Could not read {feed['name']}: {exc}")
            continue

        for item in items:
            if item["id"] in seen:
                continue

            if not relevant(item):
                continue

            combined = f"{item['title']} {item['description']}"
            prices = extract_aud_prices(combined)

            if not prices:
                print(f"Oura deal found but no usable price: {item['title']}")
                continue

            price = min(prices)
            label = classify(price)

            if label:
                send_ntfy(
                    f"{label}: A${price:.2f}",
                    (
                        f"{item['title']}\n\n"
                        f"Detected price: A${price:.2f}\n"
                        f"Source: {feed['name']}\n\n"
                        f"Tap to open the deal."
                    ),
                    item["link"],
                )

                seen.add(item["id"])
                save_seen(seen)

                print(f"Alert sent: {item['title']} - A${price:.2f}")

        time.sleep(2)


if __name__ == "__main__":
    main()
