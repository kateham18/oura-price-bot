import os
import re
import json
import html
import hashlib
from pathlib import Path

import requests


# ============================================================
# USER SETTINGS
# ============================================================

NTFY_TOPIC = os.environ["NTFY_TOPIC"]

# Thresholds are EFFECTIVE AUD COST.
#
# AU purchase:
#   advertised AUD price
#
# US purchase:
#   USD item price
#   + estimated Georgia sales tax
#   then converted to AUD

GOOD_DEAL_AUD = 650.00
GREAT_DEAL_AUD = 600.00
PRICE_ERROR_AUD = 550.00

# Estimated Georgia sales tax.
GA_SALES_TAX = 0.08

STATE_FILE = Path("seen_deals.json")


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ============================================================
# EXACT TARGET GOLD PAGES
# ============================================================

TARGET_GOLD = [
    {
        "size": 6,
        "url": "https://www.target.com/p/-/A-95006350",
    },
    {
        "size": 7,
        "url": "https://www.target.com/p/-/A-95006341",
    },
    {
        "size": 8,
        "url": "https://www.target.com/p/-/A-95006370",
    },
    {
        "size": 9,
        "url": "https://www.target.com/p/-/A-95006360",
    },
    {
        "size": 10,
        "url": "https://www.target.com/p/-/A-95006380",
    },
    {
        "size": 11,
        "url": "https://www.target.com/p/-/A-95006355",
    },
    {
        "size": 12,
        "url": "https://www.target.com/p/-/A-95006381",
    },
    {
        "size": 13,
        "url": "https://www.target.com/p/-/A-95006326",
    },
]


# ============================================================
# RETAILERS
# ============================================================
#
# AMAZON IS INTENTIONALLY NOT HERE.
#
# We are not scraping Amazon search pages because they contain:
# - sizing kits
# - accessories
# - other Oura generations
# - multiple variant prices
#
# Amazon will be covered separately with a dedicated
# product-specific tracker.
#
# ============================================================

SOURCES = [

    # ---------------- AUSTRALIA ----------------

    {
        "name": "JB Hi-Fi Australia",
        "url": (
            "https://www.jbhifi.com.au/search"
            "?query=oura%20ring%205%20gold"
        ),
        "currency": "AUD",
        "parser": "strict_search",
    },

    {
        "name": "Harvey Norman Australia",
        "url": (
            "https://www.harveynorman.com.au/"
            "catalogsearch/result/?q=oura+ring+5+gold"
        ),
        "currency": "AUD",
        "parser": "strict_search",
    },


    # ---------------- UNITED STATES ----------------

    {
        "name": "Oura US",
        "url": "https://ouraring.com/store/rings/oura-ring-5",
        "currency": "USD",
        "parser": "oura_official",
    },

    {
        "name": "Best Buy US",
        "url": "https://www.bestbuy.com/site/promo/oura-ring-5",
        "currency": "USD",
        "parser": "bestbuy",
    },

    {
        "name": "Walmart US",
        "url": "https://www.walmart.com/ip/Bs13-setup1/19971706117",
        "currency": "USD",
        "parser": "walmart",
    },

    {
        "name": "Costco US",
        "url": (
            "https://www.costco.com/p/-/"
            "oura-ring-5-gold-smart-ring-exclusive-bundle-"
            "ring-additional-charger-additional-year-of-"
            "manufacturers-warranty/4201004522"
        ),
        "currency": "USD",
        "parser": "costco",
    },

    {
        "name": "Sam's Club US",
        "url": (
            "https://www.samsclub.com/ip/"
            "Oura-Ring-5/20353851114"
        ),
        "currency": "USD",
        "parser": "sams",
    },
]


# ============================================================
# DEAL FEEDS
# ============================================================

FEEDS = [
    {
        "name": "OzBargain",
        "url": "https://www.ozbargain.com.au/deals/feed",
        "currency": "AUD",
    },
]


# ============================================================
# SOURCE HEALTH
# ============================================================

source_health = []


def health(name, status, detail=""):
    source_health.append(
        {
            "name": name,
            "status": status,
            "detail": detail,
        }
    )


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
    text = html.unescape(
        text or ""
    )

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
# DOWNLOAD PAGE
# ============================================================

def fetch(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=25,
    )

    response.raise_for_status()

    return clean_text(
        response.text
    )


# ============================================================
# LIVE USD -> AUD
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

        # Fallback only if live lookup fails.
        return 1.40


# ============================================================
# PRICE HELPERS
# ============================================================

def parse_number(value):
    try:
        return float(
            value.replace(",", "")
        )

    except Exception:
        return None


def money_values(text):
    patterns = [
        r"US\$\s*([0-9,]+(?:\.[0-9]{1,2})?)",
        r"AU\$\s*([0-9,]+(?:\.[0-9]{1,2})?)",
        r"A\$\s*([0-9,]+(?:\.[0-9]{1,2})?)",
        r"\$\s*([0-9,]+(?:\.[0-9]{1,2})?)",
    ]

    values = []

    for pattern in patterns:
        matches = re.findall(
            pattern,
            text,
            flags=re.I,
        )

        for match in matches:
            value = parse_number(
                match
            )

            if (
                value is not None
                and value >= 1
            ):
                values.append(
                    value
                )

    return values


# ============================================================
# TARGET
# ============================================================

def parse_target(
    text,
    expected_size,
):
    lower = text.lower()

    required_bits = [
        "oura",
        "ring 5",
        "gold",
        f"size {expected_size}",
    ]

    if not all(
        bit in lower
        for bit in required_bits
    ):
        return []

    # Search around exact size/product context.
    size_position = lower.find(
        f"size {expected_size}"
    )

    if size_position == -1:
        return []

    start = max(
        0,
        size_position - 350,
    )

    end = min(
        len(text),
        size_position + 1000,
    )

    section = text[
        start:end
    ]

    prices = money_values(
        section
    )

    for price in prices:

        # We deliberately DO NOT impose a minimum realistic
        # ring price. If the actual verified Gold Ring 5
        # product is genuinely $20, we want the alert.
        #
        # These exclusions are known common non-product values.
        if price in (
            5.99,
            10.00,
            69.99,
        ):
            continue

        return [
            {
                "size": expected_size,
                "price": price,
            }
        ]

    return []


# ============================================================
# BEST BUY
# ============================================================

def parse_bestbuy(text):
    results = []

    for size in range(
        6,
        14,
    ):

        # Require all of:
        # Ring 5
        # exact size
        # Gold
        # price very close to that product block

        pattern = (
            rf"Oura"
            rf".{{0,100}}?"
            rf"Ring\s*5"
            rf".{{0,300}}?"
            rf"Size\s*{size}"
            rf".{{0,180}}?"
            rf"Gold"
            rf".{{0,300}}?"
            rf"\$\s*"
            rf"([0-9,]+(?:\.[0-9]{{1,2}})?)"
        )

        match = re.search(
            pattern,
            text,
            flags=re.I | re.S,
        )

        if not match:
            continue

        price = parse_number(
            match.group(1)
        )

        if price is None:
            continue

        results.append(
            {
                "size": size,
                "price": price,
            }
        )

    return results


# ============================================================
# WALMART
# ============================================================

def parse_walmart(text):
    lower = text.lower()

    # Very strict product identity.
    required = [
        "oura",
        "ring 5",
        "gold",
    ]

    if not all(
        word in lower
        for word in required
    ):
        return []

    # The specific Walmart page should be the Gold Ring 5,
    # NOT a sizing kit or cover.
    forbidden = [
        "sizing kit only",
        "replacement charger only",
        "silicone cover only",
    ]

    if any(
        phrase in lower
        for phrase in forbidden
    ):
        return []

    results = []

    # Walmart often renders:
    # Size X, $499.00

    matches = re.findall(
        r"(?:size\s*)?"
        r"(6|7|8|9|10|11|12|13)"
        r"\s*,?\s*"
        r"\$\s*"
        r"([0-9,]+(?:\.[0-9]{1,2})?)",
        text,
        flags=re.I,
    )

    for size, raw_price in matches:

        price = parse_number(
            raw_price
        )

        if price is None:
            continue

        results.append(
            {
                "size": int(size),
                "price": price,
            }
        )

    # Selected variant fallback.
    if not results:

        patterns = [
            (
                r"Current price is\s*"
                r"(?:USD)?\$?\s*"
                r"([0-9,]+(?:\.[0-9]{1,2})?)"
            ),
            (
                r"Now\s*\$\s*"
                r"([0-9,]+(?:\.[0-9]{1,2})?)"
            ),
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                text,
                flags=re.I,
            )

            if not match:
                continue

            price = parse_number(
                match.group(1)
            )

            if price is not None:

                results.append(
                    {
                        "size": None,
                        "price": price,
                    }
                )

                break

    return results


# ============================================================
# OURA OFFICIAL
# ============================================================

def parse_oura_official(text):
    lower = text.lower()

    # Find Gold section.
    gold_index = lower.find(
        "gold"
    )

    if gold_index == -1:
        return []

    # Only inspect a small region AFTER Gold.
    # This stops the Silver $399 price elsewhere
    # on the page being interpreted as Gold.

    section = text[
        gold_index:
        gold_index + 500
    ]

    prices = money_values(
        section
    )

    for price in prices:

        if price in (
            5.99,
            69.99,
        ):
            continue

        return [
            {
                "size": None,
                "price": price,
            }
        ]

    return []


# ============================================================
# COSTCO
# ============================================================

def parse_costco(text):
    lower = text.lower()

    required = [
        "oura",
        "ring 5",
        "gold",
    ]

    if not all(
        word in lower
        for word in required
    ):
        return []

    index = lower.find(
        "oura"
    )

    section = text[
        index:
        index + 1800
    ]

    prices = money_values(
        section
    )

    for price in prices:

        if price in (
            5.99,
            10.00,
            69.99,
        ):
            continue

        return [
            {
                "size": None,
                "price": price,
            }
        ]

    return []


# ============================================================
# SAM'S CLUB
# ============================================================

def parse_sams(text):
    lower = text.lower()

    required = [
        "oura",
        "ring 5",
        "gold",
    ]

    if not all(
        word in lower
        for word in required
    ):
        return []

    index = lower.find(
        "oura"
    )

    section = text[
        index:
        index + 1800
    ]

    prices = money_values(
        section
    )

    for price in prices:

        if price in (
            5.99,
            10.00,
            69.99,
        ):
            continue

        return [
            {
                "size": None,
                "price": price,
            }
        ]

    return []


# ============================================================
# STRICT SEARCH
#
# ONLY used for AU retailers where we haven't yet got
# dependable individual variant URLs.
#
# This is much tighter than the Amazon version that caused
# the false alerts.
# ============================================================

def parse_strict_search(text):
    lower = text.lower()

    results = []

    # Look for product title.
    search_terms = [
        "oura ring 5",
        "oura ring5",
    ]

    positions = []

    for term in search_terms:
        start = 0

        while True:

            index = lower.find(
                term,
                start,
            )

            if index == -1:
                break

            positions.append(
                index
            )

            start = (
                index
                + len(term)
            )

    for index in sorted(
        set(positions)
    ):

        # Very tight product-card window.
        window = text[
            max(0, index - 60):
            min(len(text), index + 450)
        ]

        window_lower = window.lower()

        if "gold" not in window_lower:
            continue

        # Explicitly reject accessories.
        bad_phrases = [
            "sizing kit",
            "charger",
            "charging case",
            "replacement charger",
            "ring protector",
            "silicone cover",
            "cover for oura",
            "protective cover",
            "case for oura",
        ]

        if any(
            bad in window_lower
            for bad in bad_phrases
        ):
            continue

        prices = money_values(
            window
        )

        if not prices:
            continue

        # We take first price attached to this
        # tightly-bound product result.

        for price in prices:

            if price in (
                5.99,
                10.00,
                69.99,
            ):
                continue

            results.append(
                {
                    "size": None,
                    "price": price,
                }
            )

            break

    return results


# ============================================================
# PRICE CLASSIFICATION
# ============================================================

def classification(aud_total):

    if aud_total <= PRICE_ERROR_AUD:
        return (
            "POSSIBLE PRICE ERROR",
            "🚨",
        )

    if aud_total <= GREAT_DEAL_AUD:
        return (
            "GREAT DEAL",
            "🔥",
        )

    if aud_total <= GOOD_DEAL_AUD:
        return (
            "GOOD DEAL",
            "💍",
        )

    return (
        None,
        "",
    )


# ============================================================
# EFFECTIVE AUD COST
# ============================================================

def effective_aud(
    item_price,
    currency,
    usd_to_aud,
):

    if currency == "AUD":
        return item_price

    taxed_usd = (
        item_price
        * (1 + GA_SALES_TAX)
    )

    return (
        taxed_usd
        * usd_to_aud
    )


# ============================================================
# UNIQUE ALERT ID
# ============================================================

def deal_id(
    retailer,
    size,
    price,
):

    raw = (
        f"{retailer}|"
        f"{size}|"
        f"{price:.2f}"
    )

    return hashlib.sha256(
        raw.encode(
            "utf-8"
        )
    ).hexdigest()


# ============================================================
# SEND NTFY ALERT
# ============================================================

def send_notification(
    retailer,
    size,
    item_price,
    currency,
    aud_total,
    classification_name,
    emoji,
    url,
    usd_to_aud,
):

    # ASCII only in HTTP title.
    safe_title = (
        f"{classification_name} - "
        f"A${aud_total:.0f}"
    )

    if size:
        size_line = (
            f"Size: {size}\n"
        )
    else:
        size_line = ""

    if currency == "USD":

        tax_amount = (
            item_price
            * GA_SALES_TAX
        )

        taxed_usd = (
            item_price
            + tax_amount
        )

        body = (
            f"{emoji} {classification_name}\n\n"
            f"Gold Oura Ring 5\n"
            f"Retailer: {retailer}\n"
            f"{size_line}"
            f"Item price: US${item_price:.2f}\n"
            f"Estimated Georgia tax: "
            f"US${tax_amount:.2f}\n"
            f"Estimated US checkout: "
            f"US${taxed_usd:.2f}\n"
            f"USD/AUD: {usd_to_aud:.4f}\n\n"
            f"Estimated effective cost: "
            f"A${aud_total:.2f}\n\n"
            f"Tap to verify immediately."
        )

    else:

        body = (
            f"{emoji} {classification_name}\n\n"
            f"Gold Oura Ring 5\n"
            f"Retailer: {retailer}\n"
            f"{size_line}"
            f"Price: A${item_price:.2f}\n\n"
            f"Estimated effective cost: "
            f"A${aud_total:.2f}\n\n"
            f"Tap to verify immediately."
        )

    response = requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=body.encode(
            "utf-8"
        ),
        headers={
            "Title": safe_title,
            "Priority": "urgent",
            "Click": url,
            "Tags": "ring,moneybag",
        },
        timeout=15,
    )

    response.raise_for_status()


# ============================================================
# HANDLE VERIFIED RESULT
# ============================================================

def evaluate_result(
    retailer,
    url,
    currency,
    size,
    price,
    usd_to_aud,
    seen,
):

    aud_total = effective_aud(
        price,
        currency,
        usd_to_aud,
    )

    label, emoji = classification(
        aud_total
    )

    size_display = (
        f"Size {size}"
        if size
        else "Size unknown/all"
    )

    if currency == "USD":

        print(
            f"{retailer} | "
            f"{size_display} | "
            f"US${price:.2f} | "
            f"est A${aud_total:.2f}"
        )

    else:

        print(
            f"{retailer} | "
            f"{size_display} | "
            f"A${price:.2f}"
        )

    # Price is legitimate but not cheap enough.
    if not label:
        return False

    unique_id = deal_id(
        retailer,
        size,
        price,
    )

    if unique_id in seen:

        print(
            "Already alerted for this exact price."
        )

        return False

    send_notification(
        retailer=retailer,
        size=size,
        item_price=price,
        currency=currency,
        aud_total=aud_total,
        classification_name=label,
        emoji=emoji,
        url=url,
        usd_to_aud=usd_to_aud,
    )

    seen.add(
        unique_id
    )

    save_seen(
        seen
    )

    print(
        "ALERT SENT"
    )

    return True


# ============================================================
# TARGET CHECK
# ============================================================

def check_target(
    usd_to_aud,
    seen,
):

    retailer_name = (
        "Target US"
    )

    successes = 0
    failures = 0

    for product in TARGET_GOLD:

        size = product["size"]
        url = product["url"]

        print(
            f"\nChecking Target "
            f"Gold size {size}..."
        )

        try:

            text = fetch(
                url
            )

        except Exception as exc:

            print(
                f"BLOCKED/ERROR: "
                f"Target size {size}: "
                f"{exc}"
            )

            failures += 1

            continue

        results = parse_target(
            text,
            size,
        )

        if not results:

            print(
                f"No verified Gold price "
                f"found for Target size {size}."
            )

            failures += 1

            continue

        successes += 1

        for result in results:

            evaluate_result(
                retailer=retailer_name,
                url=url,
                currency="USD",
                size=result["size"],
                price=result["price"],
                usd_to_aud=usd_to_aud,
                seen=seen,
            )

    if successes > 0:

        health(
            retailer_name,
            "OK",
            (
                f"{successes} Gold size pages "
                f"verified"
            ),
        )

    else:

        health(
            retailer_name,
            "NO VERIFIED PRODUCT",
            (
                f"{failures} pages failed "
                f"or could not be parsed"
            ),
        )


# ============================================================
# OTHER RETAILER CHECK
# ============================================================

def check_source(
    source,
    usd_to_aud,
    seen,
):

    name = source["name"]

    print(
        f"\nChecking {name}..."
    )

    try:

        text = fetch(
            source["url"]
        )

    except Exception as exc:

        print(
            f"BLOCKED/ERROR: "
            f"{name}: {exc}"
        )

        health(
            name,
            "BLOCKED",
            str(exc),
        )

        return

    parser_name = source["parser"]

    if parser_name == "bestbuy":
        results = parse_bestbuy(
            text
        )

    elif parser_name == "walmart":
        results = parse_walmart(
            text
        )

    elif parser_name == "oura_official":
        results = parse_oura_official(
            text
        )

    elif parser_name == "costco":
        results = parse_costco(
            text
        )

    elif parser_name == "sams":
        results = parse_sams(
            text
        )

    elif parser_name == "strict_search":
        results = parse_strict_search(
            text
        )

    else:
        results = []

    if not results:

        print(
            f"No verified Gold Ring 5 "
            f"price found at {name}."
        )

        health(
            name,
            "NO VERIFIED PRODUCT",
            (
                "Page loaded but parser did "
                "not confirm Gold Ring 5 + price"
            ),
        )

        return

    health(
        name,
        "OK",
        (
            f"{len(results)} verified "
            f"price result(s)"
        ),
    )

    combinations = set()

    for result in results:

        combination = (
            result["size"],
            result["price"],
        )

        if combination in combinations:
            continue

        combinations.add(
            combination
        )

        evaluate_result(
            retailer=name,
            url=source["url"],
            currency=source["currency"],
            size=result["size"],
            price=result["price"],
            usd_to_aud=usd_to_aud,
            seen=seen,
        )


# ============================================================
# OZBARGAIN
# ============================================================

def check_ozbargain(
    usd_to_aud,
    seen,
):

    name = "OzBargain"
    url = FEEDS[0]["url"]

    print(
        "\nChecking OzBargain..."
    )

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20,
        )

        response.raise_for_status()

    except Exception as exc:

        print(
            f"BLOCKED/ERROR: "
            f"OzBargain: {exc}"
        )

        health(
            name,
            "BLOCKED",
            str(exc),
        )

        return

    items = re.findall(
        r"<item>(.*?)</item>",
        response.text,
        flags=re.I | re.S,
    )

    matches_found = 0

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

        description_match = re.search(
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
            description_match.group(1)
            if description_match
            else ""
        )

        link = clean_text(
            link_match.group(1)
            if link_match
            else url
        )

        combined = (
            f"{title} {description}"
        )

        lower = combined.lower()

        if (
            "oura ring 5" not in lower
            or
            "gold" not in lower
        ):
            continue

        bad_phrases = [
            "sizing kit",
            "charger",
            "cover",
            "protector",
        ]

        if any(
            phrase in lower
            for phrase in bad_phrases
        ):
            continue

        prices = money_values(
            combined
        )

        if not prices:
            continue

        price = None

        for candidate in prices:

            if candidate in (
                5.99,
                10.00,
                69.99,
            ):
                continue

            price = candidate
            break

        if price is None:
            continue

        matches_found += 1

        evaluate_result(
            retailer=name,
            url=link,
            currency="AUD",
            size=None,
            price=price,
            usd_to_aud=usd_to_aud,
            seen=seen,
        )

    health(
        name,
        "OK",
        (
            f"Feed checked; "
            f"{matches_found} matching "
            f"Gold Ring 5 deal(s)"
        ),
    )


# ============================================================
# PRINT HEALTH REPORT
# ============================================================

def print_health_report():

    print(
        "\n"
        "========================================"
    )

    print(
        "SOURCE HEALTH REPORT"
    )

    print(
        "========================================"
    )

    for item in source_health:

        print(
            f"{item['status']} | "
            f"{item['name']}"
        )

        if item["detail"]:

            print(
                f"  {item['detail']}"
            )

    print(
        "\nAmazon AU: EXTERNAL TRACKER"
    )

    print(
        "Amazon US: EXTERNAL TRACKER"
    )

    print(
        "Amazon intentionally not scraped "
        "by GitHub bot."
    )

    print(
        "========================================"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "Starting STRICT Gold Oura Ring 5 monitor..."
    )

    print(
        "\nAlert thresholds:"
    )

    print(
        "GOOD DEAL: A$650 or less"
    )

    print(
        "GREAT DEAL: A$600 or less"
    )

    print(
        "POSSIBLE PRICE ERROR: A$550 or less"
    )

    print(
        "\nIMPORTANT:"
    )

    print(
        "There is NO minimum price."
    )

    print(
        "A verified Gold Ring 5 at A$20 "
        "would still trigger."
    )

    print(
        "\nAmazon AU/US are excluded from "
        "direct scraping to prevent false positives."
    )

    seen = load_seen()

    usd_to_aud = get_usd_to_aud()

    print(
        f"\nUSD -> AUD: "
        f"{usd_to_aud:.4f}"
    )

    print(
        "US calculations include estimated "
        "8% Georgia sales tax."
    )

    check_target(
        usd_to_aud,
        seen,
    )

    for source in SOURCES:

        check_source(
            source,
            usd_to_aud,
            seen,
        )

    check_ozbargain(
        usd_to_aud,
        seen,
    )

    print_health_report()

    print(
        "\nSearch complete."
    )


if __name__ == "__main__":
    main()
