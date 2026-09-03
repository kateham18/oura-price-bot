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
#
GOOD_DEAL_AUD = 650.00
GREAT_DEAL_AUD = 600.00
PRICE_ERROR_AUD = 550.00

# Conservative estimate for delivery in Georgia.
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
# OTHER SOURCES
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

    {
        "name": "Amazon Australia",
        "url": (
            "https://www.amazon.com.au/"
            "s?k=Oura+Ring+5+Gold"
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
        "url": "https://www.walmart.com/ip/19953755891",
        "currency": "USD",
        "parser": "walmart",
    },

    {
        "name": "Amazon US",
        "url": (
            "https://www.amazon.com/"
            "s?k=Oura+Ring+5+Gold"
        ),
        "currency": "USD",
        "parser": "strict_search",
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
        "url": "https://www.samsclub.com/ip/Oura-Ring-5/20353851114",
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
# SAVED ALERT HISTORY
# ============================================================

def load_seen():
    if not STATE_FILE.exists():
        return set()

    try:
        return set(json.loads(STATE_FILE.read_text()))
    except Exception:
        return set()


def save_seen(seen):
    STATE_FILE.write_text(
        json.dumps(sorted(seen), indent=2)
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
# DOWNLOAD PAGE
# ============================================================

def fetch(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=25,
    )

    response.raise_for_status()

    return clean_text(response.text)


# ============================================================
# LIVE USD -> AUD RATE
# ============================================================

def get_usd_to_aud():
    try:
        response = requests.get(
            "https://api.frankfurter.app/latest?from=USD&to=AUD",
            timeout=15,
        )

        response.raise_for_status()

        data = response.json()

        return float(data["rates"]["AUD"])

    except Exception as exc:
        print(f"FX lookup failed: {exc}")

        # Only used if live rate lookup fails.
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
            value = parse_number(match)

            if value is not None and value >= 1:
                values.append(value)

    return values


def valid_ring_price_context(text):
    lower = text.lower()

    required = (
        "oura ring 5" in lower
        and
        "gold" in lower
    )

    if not required:
        return False

    bad_phrases = [
        "charging case",
        "charger only",
        "replacement charger",
        "ring protector",
        "silicone protector",
        "membership",
    ]

    # We don't reject "sizing kit" globally because
    # Best Buy includes those words in the REAL Ring 5 title.
    for phrase in bad_phrases:
        if phrase in lower:
            return False

    return True


# ============================================================
# BEST BUY
# ============================================================

def parse_bestbuy(text):
    results = []

    for size in range(6, 14):

        pattern = (
            rf"Oura\s*-\s*Ring 5"
            rf".{{0,250}}?"
            rf"Size {size}"
            rf".{{0,100}}?"
            rf"Gold"
            rf".{{0,450}}?"
            rf"\$\s*([0-9,]+(?:\.[0-9]{{1,2}})?)"
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

    if (
        "oura ring 5 gold" not in lower
        or
        "sold and shipped by walmart" not in lower
    ):
        return []

    results = []

    # Walmart exposes variants in forms such as:
    # 6, $499.00
    # 7, $499.00
    # etc.
    matches = re.findall(
        r"\b(6|7|8|9|10|11|12|13)"
        r"\s*,\s*"
        r"\$\s*([0-9,]+(?:\.[0-9]{1,2})?)",
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

    # Fallback for the selected Gold variant.
    if not results:

        match = re.search(
            r"Current price is\s*USD?\$?"
            r"\s*([0-9,]+(?:\.[0-9]{1,2})?)",
            text,
            flags=re.I,
        )

        if match:
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

    return results


# ============================================================
# TARGET EXACT GOLD PRODUCT PAGE
# ============================================================

def parse_target(text, expected_size):
    expected_title = (
        f"oura ring 5 gold - size {expected_size}"
    )

    lower = text.lower()

    if expected_title not in lower:
        return []

    # Only inspect the beginning of the page around
    # the confirmed Gold + exact-size title.
    index = lower.find(expected_title)

    section = text[
        index:index + 1000
    ]

    prices = money_values(
        section
    )

    filtered = []

    for price in prices:

        # Ignore obvious financing/monthly/gift-card values.
        if price in (10, 47, 99, 124.75):
            continue

        filtered.append(price)

    if not filtered:
        return []

    return [
        {
            "size": expected_size,
            "price": filtered[0],
        }
    ]


# ============================================================
# OURA OFFICIAL
# ============================================================

def parse_oura_official(text):
    # Require a price appearing AFTER the Gold finish label.
    #
    # This prevents Silver $399 appearing earlier on the page
    # from being reported as Gold.
    matches = re.findall(
        r"\bGold\b"
        r".{0,300}?"
        r"\$\s*([0-9,]+(?:\.[0-9]{1,2})?)",
        text,
        flags=re.I | re.S,
    )

    results = []

    for raw_price in matches:
        price = parse_number(
            raw_price
        )

        if price is None:
            continue

        # Exclude common membership/payment figures.
        if price in (5.99, 69.99):
            continue

        results.append(
            {
                "size": None,
                "price": price,
            }
        )

    return results[:1]


# ============================================================
# COSTCO GOLD
# ============================================================

def parse_costco(text):
    lower = text.lower()

    if (
        "oura ring 5 gold smart ring" not in lower
        or
        "color gold" not in lower
    ):
        return []

    title_index = lower.find(
        "oura ring 5 gold smart ring"
    )

    section = text[
        title_index:title_index + 1800
    ]

    prices = money_values(
        section
    )

    results = []

    for price in prices:

        if price in (
            5.99,
            10,
            69.99,
        ):
            continue

        results.append(
            {
                "size": None,
                "price": price,
            }
        )

    return results[:1]


# ============================================================
# SAM'S CLUB GOLD
# ============================================================

def parse_sams(text):
    lower = text.lower()

    if (
        "oura ring 5" not in lower
        or
        "actual color:gold" not in lower.replace(" ", "")
    ):
        # Try normal spacing too.
        if (
            "oura ring 5" not in lower
            or
            "actual color: gold" not in lower
        ):
            return []

    # Sam's may hide member price depending on session.
    prices = money_values(
        text[:2500]
    )

    results = []

    for price in prices:

        if price in (
            5.99,
            10,
            69.99,
        ):
            continue

        results.append(
            {
                "size": None,
                "price": price,
            }
        )

    return results[:1]


# ============================================================
# STRICT GENERIC SEARCH
# Used only when retailer doesn't give us a dependable
# dedicated product-page format.
# ============================================================

def parse_strict_search(text):
    lower = text.lower()

    results = []

    phrase = "oura ring 5"

    start = 0

    while True:

        index = lower.find(
            phrase,
            start,
        )

        if index == -1:
            break

        # Tight window only.
        window = text[
            max(0, index - 80):
            min(len(text), index + 500)
        ]

        window_lower = window.lower()

        # Gold has to be inside THIS same product window.
        if "gold" not in window_lower:
            start = index + len(phrase)
            continue

        bad = [
            "charging case",
            "charger only",
            "replacement charger",
            "protector",
        ]

        if any(
            phrase in window_lower
            for phrase in bad
        ):
            start = index + len(phrase)
            continue

        prices = money_values(
            window
        )

        for price in prices:

            if price in (
                5.99,
                10,
                69.99,
                99,
            ):
                continue

            results.append(
                {
                    "size": None,
                    "price": price,
                }
            )

            # Only use the first price after this exact
            # product context.
            break

        start = index + len(phrase)

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
# EFFECTIVE COST
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
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================
# NTFY
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

    # ASCII-only title avoids the crash from before.
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

        taxed_usd = (
            item_price
            * (1 + GA_SALES_TAX)
        )

        body = (
            f"{emoji} {classification_name}\n\n"
            f"Gold Oura Ring 5\n"
            f"Retailer: {retailer}\n"
            f"{size_line}"
            f"Item price: US${item_price:.2f}\n"
            f"Estimated GA tax: "
            f"US${item_price * GA_SALES_TAX:.2f}\n"
            f"Estimated US checkout: "
            f"US${taxed_usd:.2f}\n"
            f"USD/AUD: {usd_to_aud:.4f}\n"
            f"Estimated effective cost: "
            f"A${aud_total:.2f}\n\n"
            f"Shipping is not included unless the "
            f"retailer provides it free.\n\n"
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
        data=body.encode("utf-8"),
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
# HANDLE RESULT
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
            f"est. A${aud_total:.2f} "
            f"after GA tax"
        )

    else:

        print(
            f"{retailer} | "
            f"{size_display} | "
            f"A${price:.2f}"
        )

    if not label:
        return

    unique_id = deal_id(
        retailer,
        size,
        price,
    )

    if unique_id in seen:
        print(
            "Already alerted for this exact price."
        )
        return

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


# ============================================================
# CHECK TARGET
# ============================================================

def check_target(
    usd_to_aud,
    seen,
):

    for product in TARGET_GOLD:

        size = product["size"]
        url = product["url"]

        print(
            f"\nChecking Target US "
            f"Gold size {size}..."
        )

        try:
            text = fetch(url)

        except Exception as exc:
            print(
                f"SKIPPED Target size {size}: "
                f"{exc}"
            )
            continue

        results = parse_target(
            text,
            size,
        )

        if not results:
            print(
                f"No verified Gold price found "
                f"for Target size {size}."
            )
            continue

        for result in results:

            evaluate_result(
                retailer="Target US",
                url=url,
                currency="USD",
                size=result["size"],
                price=result["price"],
                usd_to_aud=usd_to_aud,
                seen=seen,
            )


# ============================================================
# CHECK OTHER RETAILERS
# ============================================================

def check_source(
    source,
    usd_to_aud,
    seen,
):

    print(
        f"\nChecking {source['name']}..."
    )

    try:
        text = fetch(
            source["url"]
        )

    except Exception as exc:

        print(
            f"SKIPPED {source['name']} "
            f"(blocked/error): {exc}"
        )

        return

    parser_name = source["parser"]

    if parser_name == "bestbuy":
        results = parse_bestbuy(text)

    elif parser_name == "walmart":
        results = parse_walmart(text)

    elif parser_name == "oura_official":
        results = parse_oura_official(text)

    elif parser_name == "costco":
        results = parse_costco(text)

    elif parser_name == "sams":
        results = parse_sams(text)

    elif parser_name == "strict_search":
        results = parse_strict_search(text)

    else:
        results = []

    if not results:

        print(
            f"No STRICT verified Gold Ring 5 "
            f"price found at {source['name']}."
        )

        return

    seen_combinations = set()

    for result in results:

        combination = (
            result["size"],
            result["price"],
        )

        if combination in seen_combinations:
            continue

        seen_combinations.add(
            combination
        )

        evaluate_result(
            retailer=source["name"],
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

    feed = FEEDS[0]

    print(
        "\nChecking OzBargain..."
    )

    try:
        response = requests.get(
            feed["url"],
            headers=HEADERS,
            timeout=20,
        )

        response.raise_for_status()

    except Exception as exc:

        print(
            f"SKIPPED OzBargain: {exc}"
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
            f"{title} {description}"
        )

        lower = combined.lower()

        if (
            "oura ring 5" not in lower
            or
            "gold" not in lower
        ):
            continue

        if any(
            phrase in lower
            for phrase in [
                "charging case",
                "charger only",
                "ring protector",
            ]
        ):
            continue

        prices = money_values(
            combined
        )

        if not prices:
            continue

        # For an actual deal post, use the first plausible
        # advertised price.
        price = None

        for candidate in prices:

            if candidate in (
                5.99,
                10,
                69.99,
                99,
            ):
                continue

            price = candidate
            break

        if price is None:
            continue

        evaluate_result(
            retailer="OzBargain",
            url=link,
            currency="AUD",
            size=None,
            price=price,
            usd_to_aud=usd_to_aud,
            seen=seen,
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "Starting STRICT Gold Oura Ring 5 search..."
    )

    print(
        "\nEffective AUD thresholds:"
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
        "\nUS comparison assumes:"
    )

    print(
        "Delivery to Georgia"
    )

    print(
        "Estimated sales tax: 8%"
    )

    print(
        "\nAustralian comparison assumes:"
    )

    print(
        "Delivery to Victoria"
    )

    seen = load_seen()

    usd_to_aud = (
        get_usd_to_aud()
    )

    print(
        f"\nUSD/AUD rate: "
        f"{usd_to_aud:.4f}"
    )

    # Exact Target Gold pages, sizes 6-13.
    check_target(
        usd_to_aud,
        seen,
    )

    # Other sources.
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

    print(
        "\nSearch complete."
    )


if __name__ == "__main__":
    main()
