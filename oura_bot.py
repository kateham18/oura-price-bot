import os
import re
import json
import html
import hashlib
from pathlib import Path

import requests

NTFY_TOPIC = os.environ["NTFY_TOPIC"]

GOOD_DEAL_AUD = 650
GREAT_DEAL_AUD = 600
PRICE_ERROR_AUD = 550

STATE_FILE = Path("seen_deals.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

SOURCES = [
    {
        "name": "JB Hi-Fi Australia",
        "url": "https://www.jbhifi.com.au/collections/health-fitness-wearables/oura-ring-5",
        "currency": "AUD",
    },
    {
        "name": "Harvey Norman Australia",
        "url": "https://www.harveynorman.com.au/catalogsearch/result/?q=oura+ring+5+gold",
        "currency": "AUD",
    },
    {
        "name": "Amazon Australia",
        "url": "https://www.amazon.com.au/s?k=Oura+Ring+5+Gold",
        "currency": "AUD",
    },
    {
        "name": "Oura US",
        "url": "https://ouraring.com/store/rings/oura-ring-5",
        "currency": "USD",
    },
    {
        "name": "Best Buy US",
        "url": "https://www.bestbuy.com/site/searchpage.jsp?st=oura+ring+5+gold",
        "currency": "USD",
    },
    {
        "name": "Target US",
        "url": "https://www.target.com/s?searchTerm=oura+ring+5+gold",
        "currency": "USD",
    },
    {
        "name": "Walmart US",
        "url": "https://www.walmart.com/search?q=oura+ring+5+gold",
        "currency": "USD",
    },
    {
        "name": "Amazon US",
        "url": "https://www.amazon.com/s?k=Oura+Ring+5+Gold",
        "currency": "USD",
    },
    {
        "name": "Costco US",
        "url": "https://www.costco.com/CatalogSearch?keyword=oura+ring+5",
        "currency": "USD",
    },
    {
        "name": "Sam's Club US",
        "url": "https://www.samsclub.com/s/oura%20ring%205",
        "currency": "USD",
    },
]

FEEDS = [
    {
        "name": "OzBargain New Deals",
        "url": "https://www.ozbargain.com.au/deals/feed",
        "currency": "AUD",
    }
]


def load_seen():
    if not STATE_FILE.exists():
        return set()

    try:
        return set(json.loads(STATE_FILE.read_text()))
    except Exception:
        return set()


def save_seen(seen):
    STATE_FILE.write_text(json.dumps(sorted(seen), indent=2))


def clean_text(text):
    text = html.unescape(text or "")
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def get_usd_to_aud():
    try:
        response = requests.get(
            "https://api.frankfurter.app/latest?from=USD&to=AUD",
            timeout=15,
        )
        response.raise_for_status()
        return float(response.json()["rates"]["AUD"])
    except Exception as exc:
        print(f"FX lookup failed: {exc}")
        return 1.40


def extract_prices(text, currency):
    if currency == "AUD":
        patterns = [
            r"A\$\s*([0-9]{3,4}(?:\.[0-9]{1,2})?)",
            r"AU\$\s*([0-9]{3,4}(?:\.[0-9]{1,2})?)",
            r"\$\s*([0-9]{3,4}(?:\.[0-9]{1,2})?)",
        ]
        minimum = 250
        maximum = 1200
    else:
        patterns = [
            r"US\$\s*([0-9]{2,4}(?:\.[0-9]{1,2})?)",
            r"\$\s*([0-9]{2,4}(?:\.[0-9]{1,2})?)",
        ]
        minimum = 150
        maximum = 900

    found = []

    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.I):
            try:
                price = float(match)
                if minimum <= price <= maximum:
                    found.append(price)
            except ValueError:
                pass

    return sorted(set(found))


def is_gold_oura(text):
    text = text.lower()
    has_oura = "oura ring 5" in text or "oura 5" in text
    has_gold = "gold" in text
    return has_oura and has_gold


def classify(aud_price):
    if aud_price <= PRICE_ERROR_AUD:
        return "🚨 POSSIBLE PRICE ERROR"
    if aud_price <= GREAT_DEAL_AUD:
        return "🔥 GREAT DEAL"
    if aud_price <= GOOD_DEAL_AUD:
        return "💍 GOOD DEAL"
    return None


def make_deal_id(source_name, url, price):
    raw = f"{source_name}|{url}|{price:.2f}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def send_notification(title, message, link):
    response = requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={
            "Title": title,
            "Priority": "urgent",
            "Click": link,
            "Tags": "ring,moneybag",
        },
        timeout=15,
    )
    response.raise_for_status()


def check_retailer(source, usd_to_aud, seen):
    try:
        response = requests.get(
            source["url"],
            headers=HEADERS,
            timeout=25,
        )
        response.raise_for_status()
    except Exception as exc:
        print(f"SKIPPED {source['name']} (blocked/error): {exc}")
        return

    text = clean_text(response.text)

    if not is_gold_oura(text):
        print(f"No Gold Oura Ring 5 detected at {source['name']}")
        return

    prices = extract_prices(text, source["currency"])

    if not prices:
        print(f"No usable price found at {source['name']}")
        return

    cheapest = min(prices)

    if source["currency"] == "USD":
        aud_price = cheapest * usd_to_aud
    else:
        aud_price = cheapest

    label = classify(aud_price)

    print(
        f"{source['name']}: "
        f"{source['currency']} {cheapest:.2f} "
        f"≈ A${aud_price:.2f}"
    )

    if not label:
        return

    deal_id = make_deal_id(
        source["name"],
        source["url"],
        cheapest,
    )

    if deal_id in seen:
        return

    if source["currency"] == "USD":
        message = (
            f"Gold Oura Ring 5 found\n\n"
            f"Retailer: {source['name']}\n"
            f"Price: US${cheapest:.2f}\n"
            f"Approx AUD: A${aud_price:.2f}\n\n"
            f"⚠️ AUD figure is before US sales tax/shipping.\n\n"
            f"Tap to check immediately."
        )
    else:
        message = (
            f"Gold Oura Ring 5 found\n\n"
            f"Retailer: {source['name']}\n"
            f"Price: A${cheapest:.2f}\n\n"
            f"Tap to check immediately."
        )

    send_notification(
        f"{label} — A${aud_price:.0f}",
        message,
        source["url"],
    )

    seen.add(deal_id)
    save_seen(seen)

    print("ALERT SENT")


def check_ozbargain(feed, seen):
    try:
        response = requests.get(
            feed["url"],
            headers=HEADERS,
            timeout=20,
        )
        response.raise_for_status()
    except Exception as exc:
        print(f"Could not read {feed['name']}: {exc}")
        return

    items = re.findall(
        r"<item>(.*?)</item>",
        response.text,
        flags=re.I | re.S,
    )

    for item in items:
        title_match = re.search(
            r"<title>(.*?)</title>",
            item,
            flags=re.I | re.S,
        )
        link_match = re.search(
            r"<link>(.*?)</link>",
            item,
            flags=re.I | re.S,
        )
        desc_match = re.search(
            r"<description>(.*?)</description>",
            item,
            flags=re.I | re.S,
        )

        title = clean_text(title_match.group(1) if title_match else "")
        description = clean_text(desc_match.group(1) if desc_match else "")
        link = clean_text(link_match.group(1) if link_match else feed["url"])

        combined = f"{title} {description}"

        if not is_gold_oura(combined):
            continue

        prices = extract_prices(combined, "AUD")

        if not prices:
            continue

        cheapest = min(prices)
        label = classify(cheapest)

        if not label:
            continue

        deal_id = make_deal_id(
            feed["name"],
            link,
            cheapest,
        )

        if deal_id in seen:
            continue

        send_notification(
            f"{label} — A${cheapest:.0f}",
            (
                f"Gold Oura Ring 5 deal posted\n\n"
                f"{title}\n\n"
                f"Detected price: A${cheapest:.2f}\n"
                f"Source: OzBargain\n\n"
                f"Tap immediately to check it."
            ),
            link,
        )

        seen.add(deal_id)
        save_seen(seen)

        print(f"OzBargain alert: {title}")


def main():
    print("Starting Gold Oura Ring 5 search...")

    seen = load_seen()
    usd_to_aud = get_usd_to_aud()

    print(f"USD/AUD rate: {usd_to_aud:.4f}")

    for source in SOURCES:
        print(f"\nChecking {source['name']}...")
        check_retailer(source, usd_to_aud, seen)

    for feed in FEEDS:
        print(f"\nChecking {feed['name']}...")
        check_ozbargain(feed, seen)

    print("\nSearch complete.")


if __name__ == "__main__":
    main()
