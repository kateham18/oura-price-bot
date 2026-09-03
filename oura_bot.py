import os
import re
import json
import html
import hashlib
from pathlib import Path

import requests


# ============================================================
# SETTINGS
# ============================================================

NTFY_TOPIC = os.environ["NTFY_TOPIC"]

# These are MAXIMUM prices.
# Anything BELOW them also qualifies.
GOOD_DEAL_AUD = 650.00
GREAT_DEAL_AUD = 600.00
PRICE_ERROR_AUD = 550.00

STATE_FILE = Path("seen_deals.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ============================================================
# RETAILERS TO CHECK
# ============================================================

SOURCES = [

    # ---------------- AUSTRALIA ----------------

    {
        "name": "JB Hi-Fi Australia",
        "url": "https://www.jbhifi.com.au/collections/health-fitness-wearables/oura-ring-5",
        "currency": "AUD",
        "country": "AU",
    },

    {
        "name": "Harvey Norman Australia",
        "url": "https://www.harveynorman.com.au/catalogsearch/result/?q=oura+ring+5+gold",
        "currency": "AUD",
        "country": "AU",
    },

    {
        "name": "Amazon Australia",
        "url": "https://www.amazon.com.au/s?k=Oura+Ring+5+Gold",
        "currency": "AUD",
        "country": "AU",
    },


    # ---------------- UNITED STATES ----------------

    {
        "name": "Oura US",
        "url": "https://ouraring.com/store/rings/oura-ring-5",
        "currency": "USD",
        "country": "US",
    },

    {
        "name": "Best Buy US",
        "url": "https://www.bestbuy.com/site/searchpage.jsp?st=oura+ring+5+gold",
        "currency": "USD",
        "country": "US",
    },

    {
        "name": "Target US",
        "url": "https://www.target.com/s?searchTerm=oura+ring+5+gold",
        "currency": "USD",
        "country": "US",
    },

    {
        "name": "Walmart US",
        "url": "https://www.walmart.com/search?q=oura+ring+5+gold",
        "currency": "USD",
        "country": "US",
    },

    {
        "name": "Amazon US",
        "url": "https://www.amazon.com/s?k=Oura+Ring+5+Gold",
        "currency": "USD",
        "country": "US",
    },

    {
        "name": "Costco US",
        "url": "https://www.costco.com/CatalogSearch?keyword=oura+ring+5",
        "currency": "USD",
        "country": "US",
    },

    {
        "name": "Sam's Club US",
        "url": "https://www.samsclub.com/s/oura%20ring%205",
        "currency": "USD",
        "country": "US",
    },
]


# ============================================================
# DEAL FEEDS
# ============================================================

FEEDS = [

    {
        "name": "OzBargain New Deals",
        "url": "https://www.ozbargain.com.au/deals/feed",
        "currency": "AUD",
        "country": "AU",
    },

]


# ============================================================
# WORDS USED TO AVOID FALSE ALERTS
# ============================================================

ACCESSORY_WORDS = [
    "sizing kit",
    "size kit",
    "sizing rings",
    "charger only",
    "charging dock",
    "replacement charger",
    "charging cable",
    "ring protector",
    "ring cover",
    "silicone protector",
    "case only",
]


# ============================================================
# SAVED ALERT HISTORY
# ============================================================

def load_seen():

    if not STATE_FILE.exists():
        return set()

    try:
        return set(
            json.loads(
                STATE_FILE.read_text()
            )
        )

    except Exception:
        return set()


def save_seen(seen):

    STATE_FILE.write_text(
        json.dumps(
            sorted(seen),
            indent=2,
        )
    )


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text):

    text = html.unescape(text or "")

    text = re.sub(
        r"<script.*?</script>",
        " ",
        text,
        flags=re.I | re.S,
    )

    text = re.sub(
        r"<style.*?</style>",
        " ",
        text,
        flags=re.I | re.S,
    )

    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# LIVE USD -> AUD EXCHANGE RATE
# ============================================================

def get_usd_to_aud():

    try:

        response = requests.get(
            "https://api.frankfurter.app/latest?from=USD&to=AUD",
            timeout=15,
        )

        response.raise_for_status()

        data = response.json()

        return float(
            data["rates"]["AUD"]
        )

    except Exception as exc:

        print(
            f"FX lookup failed: {exc}"
        )

        # Fallback only if live FX lookup fails
        return 1.40


# ============================================================
# DETECT THE RIGHT PRODUCT
# ============================================================

def contains_gold_oura(text):

    text = text.lower()

    has_oura = (
        "oura ring 5" in text
        or
        "oura 5" in text
    )

    has_gold = (
        "gold" in text
    )

    return (
        has_oura
        and
        has_gold
    )


# ============================================================
# REMOVE ACCESSORY-ONLY AREAS
# ============================================================

def is_accessory_text(text):

    text = text.lower()

    return any(
        word in text
        for word in ACCESSORY_WORDS
    )


# ============================================================
# FIND PRODUCT-RELEVANT TEXT WINDOWS
# ============================================================

def get_product_windows(text):

    lower_text = text.lower()

    windows = []

    search_terms = [
        "oura ring 5",
        "oura 5",
    ]

    for term in search_terms:

        start = 0

        while True:

            index = lower_text.find(
                term,
                start,
            )

            if index == -1:
                break

            # Look around the product title instead of
            # blindly examining every price on the page.
            window_start = max(
                0,
                index - 500,
            )

            window_end = min(
                len(text),
                index + 1500,
            )

            window = text[
                window_start:window_end
            ]

            windows.append(window)

            start = (
                index
                + len(term)
            )

    return windows


# ============================================================
# PRICE EXTRACTION
# ============================================================

def extract_prices(text, currency):

    if currency == "AUD":

        patterns = [
            r"A\$\s*([0-9]{1,4}(?:\.[0-9]{1,2})?)",
            r"AU\$\s*([0-9]{1,4}(?:\.[0-9]{1,2})?)",
            r"\$\s*([0-9]{1,4}(?:\.[0-9]{1,2})?)",
        ]

        maximum = 1500.00

    else:

        patterns = [
            r"US\$\s*([0-9]{1,4}(?:\.[0-9]{1,2})?)",
            r"\$\s*([0-9]{1,4}(?:\.[0-9]{1,2})?)",
        ]

        maximum = 1000.00

    found = []

    for pattern in patterns:

        matches = re.findall(
            pattern,
            text,
            flags=re.I,
        )

        for match in matches:

            try:

                price = float(match)

                # IMPORTANT:
                # There is deliberately NO meaningful
                # lower price limit here.
                #
                # A Ring at $99, $50 or even $1 could
                # therefore be detected as a price error.
                if (
                    price >= 1.00
                    and
                    price <= maximum
                ):

                    found.append(price)

            except ValueError:
                pass

    return sorted(
        set(found)
    )


# ============================================================
# SEARCH PRODUCT WINDOWS FOR PRICES
# ============================================================

def find_gold_oura_prices(text, currency):

    prices = []

    windows = get_product_windows(text)

    for window in windows:

        lower_window = window.lower()

        # Must contain GOLD in the relevant product area.
        if "gold" not in lower_window:
            continue

        # Skip an area if it clearly appears to be
        # an accessory rather than the actual ring.
        if is_accessory_text(lower_window):

            # But don't automatically discard it if
            # it also explicitly describes the actual
            # Gold Ring 5.
            explicit_ring = (
                "oura ring 5" in lower_window
                and
                "gold" in lower_window
            )

            if not explicit_ring:
                continue

        window_prices = extract_prices(
            window,
            currency,
        )

        prices.extend(
            window_prices
        )

    return sorted(
        set(prices)
    )


# ============================================================
# DEAL CLASSIFICATION
# ============================================================

def classify(aud_price):

    # Lowest threshold checked first.

    if aud_price <= PRICE_ERROR_AUD:
        return "POSSIBLE PRICE ERROR"

    if aud_price <= GREAT_DEAL_AUD:
        return "GREAT DEAL"

    if aud_price <= GOOD_DEAL_AUD:
        return "GOOD DEAL"

    return None


def classification_emoji(aud_price):

    if aud_price <= PRICE_ERROR_AUD:
        return "🚨"

    if aud_price <= GREAT_DEAL_AUD:
        return "🔥"

    if aud_price <= GOOD_DEAL_AUD:
        return "💍"

    return ""


# ============================================================
# UNIQUE DEAL ID
# ============================================================

def make_deal_id(
    source_name,
    url,
    price,
):

    raw = (
        f"{source_name}|"
        f"{url}|"
        f"{price:.2f}"
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================
# IPHONE / NTFY NOTIFICATION
# ============================================================

def send_notification(
    classification,
    aud_price,
    message,
    link,
):

    emoji = classification_emoji(
        aud_price
    )

    # HTTP headers need ASCII-safe text.
    # This avoids the UnicodeEncodeError
    # from the previous run.
    safe_title = (
        f"{classification} - "
        f"A${aud_price:.0f}"
    )

    body = (
        f"{emoji} "
        f"{classification} - "
        f"A${aud_price:.2f}"
        f"\n\n"
        f"{message}"
    )

    response = requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=body.encode("utf-8"),
        headers={
            "Title": safe_title,
            "Priority": "urgent",
            "Click": link,
            "Tags": "ring,moneybag",
        },
        timeout=15,
    )

    response.raise_for_status()


# ============================================================
# RETAILER CHECK
# ============================================================

def check_retailer(
    source,
    usd_to_aud,
    seen,
):

    try:

        response = requests.get(
            source["url"],
            headers=HEADERS,
            timeout=25,
        )

        response.raise_for_status()

    except Exception as exc:

        print(
            f"SKIPPED "
            f"{source['name']} "
            f"(blocked/error): "
            f"{exc}"
        )

        return

    text = clean_text(
        response.text
    )

    if not contains_gold_oura(text):

        print(
            f"No Gold Oura Ring 5 "
            f"detected at "
            f"{source['name']}"
        )

        return

    prices = find_gold_oura_prices(
        text,
        source["currency"],
    )

    if not prices:

        print(
            f"Gold Oura Ring 5 text found, "
            f"but no usable ring price found at "
            f"{source['name']}"
        )

        return

    cheapest = min(prices)

    if source["currency"] == "USD":

        aud_price = (
            cheapest
            * usd_to_aud
        )

    else:

        aud_price = cheapest

    classification = classify(
        aud_price
    )

    print(
        f"{source['name']}: "
        f"{source['currency']} "
        f"{cheapest:.2f} "
        f"≈ A${aud_price:.2f}"
    )

    # Above A$650?
    # No notification.
    if not classification:
        return

    deal_id = make_deal_id(
        source["name"],
        source["url"],
        cheapest,
    )

    # Already notified at this exact
    # retailer/price combination.
    if deal_id in seen:

        print(
            "Already alerted for "
            "this price."
        )

        return

    if source["currency"] == "USD":

        message = (
            f"Gold Oura Ring 5 found\n\n"
            f"Retailer: {source['name']}\n"
            f"Price: US${cheapest:.2f}\n"
            f"Approx AUD: A${aud_price:.2f}\n\n"
            f"US total may be higher after "
            f"sales tax and/or shipping.\n\n"
            f"Tap immediately to check."
        )

    else:

        message = (
            f"Gold Oura Ring 5 found\n\n"
            f"Retailer: {source['name']}\n"
            f"Price: A${cheapest:.2f}\n\n"
            f"Tap immediately to check."
        )

    send_notification(
        classification,
        aud_price,
        message,
        source["url"],
    )

    seen.add(
        deal_id
    )

    save_seen(
        seen
    )

    print(
        "ALERT SENT"
    )


# ============================================================
# OZBARGAIN
# ============================================================

def check_ozbargain(
    feed,
    seen,
):

    try:

        response = requests.get(
            feed["url"],
            headers=HEADERS,
            timeout=20,
        )

        response.raise_for_status()

    except Exception as exc:

        print(
            f"Could not read "
            f"{feed['name']}: "
            f"{exc}"
        )

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

        title = clean_text(
            title_match.group(1)
            if title_match
            else ""
        )

        description = clean_text(
            desc_match.group(1)
            if desc_match
            else ""
        )

        link = clean_text(
            link_match.group(1)
            if link_match
            else feed["url"]
        )

        combined = (
            f"{title} "
            f"{description}"
        )

        if not contains_gold_oura(
            combined
        ):
            continue

        if (
            is_accessory_text(combined)
            and
            "gold" not in combined.lower()
        ):
            continue

        prices = extract_prices(
            combined,
            "AUD",
        )

        if not prices:
            continue

        cheapest = min(
            prices
        )

        classification = classify(
            cheapest
        )

        if not classification:
            continue

        deal_id = make_deal_id(
            feed["name"],
            link,
            cheapest,
        )

        if deal_id in seen:
            continue

        message = (
            f"Gold Oura Ring 5 deal posted\n\n"
            f"{title}\n\n"
            f"Detected price: "
            f"A${cheapest:.2f}\n"
            f"Source: OzBargain\n\n"
            f"Tap immediately to check."
        )

        send_notification(
            classification,
            cheapest,
            message,
            link,
        )

        seen.add(
            deal_id
        )

        save_seen(
            seen
        )

        print(
            f"OzBargain alert: "
            f"{title}"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "Starting Gold Oura Ring 5 search..."
    )

    print(
        "Alert thresholds:"
    )

    print(
        "GOOD DEAL: A$650 or less"
    )

    print(
        "GREAT DEAL: A$600 or less"
    )

    print(
        "POSSIBLE PRICE ERROR: "
        "A$550 or less"
    )

    seen = load_seen()

    usd_to_aud = (
        get_usd_to_aud()
    )

    print(
        f"USD/AUD rate: "
        f"{usd_to_aud:.4f}"
    )

    for source in SOURCES:

        print(
            f"\nChecking "
            f"{source['name']}..."
        )

        check_retailer(
            source,
            usd_to_aud,
            seen,
        )

    for feed in FEEDS:

        print(
            f"\nChecking "
            f"{feed['name']}..."
        )

        check_ozbargain(
            feed,
            seen,
        )

    print(
        "\nSearch complete."
    )


if __name__ == "__main__":
    main()
