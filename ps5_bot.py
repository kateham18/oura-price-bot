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

# Effective price AFTER estimated Georgia tax for US deals.
GOOD_DEAL_AUD = 700.00
GREAT_DEAL_AUD = 600.00
PRICE_ERROR_AUD = 500.00

GA_SALES_TAX = 0.08

STATE_FILE = Path("seen_ps5_deals.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ============================================================
# SOURCES
# ============================================================

SOURCES = [

    # ---------------- USA ----------------

    {
        "name": "Walmart US",
        "url": (
            "https://www.walmart.com/browse/video-games/"
            "playstation-5-ps5-consoles/"
            "2636_5170403_3475115_2762884"
        ),
        "currency": "USD",
        "parser": "walmart",
    },

    {
        "name": "Best Buy US",
        "url": (
            "https://www.bestbuy.com/site/playstation-5/"
            "ps5-consoles/pcmcat1587395025973.c"
        ),
        "currency": "USD",
        "parser": "bestbuy",
    },

    # ---------------- AUSTRALIA ----------------

    {
        "name": "JB Hi-Fi Australia",
        "url": (
            "https://www.jbhifi.com.au/search"
            "?query=playstation%205%20console"
        ),
        "currency": "AUD",
        "parser": "strict_search",
    },

    {
        "name": "Harvey Norman Australia",
        "url": (
            "https://www.harveynorman.com.au/"
            "catalogsearch/result/?q=playstation+5+console"
        ),
        "currency": "AUD",
        "parser": "strict_search",
    },

    {
        "name": "EB Games Australia",
        "url": (
            "https://www.ebgames.com.au/search"
            "?q=playstation%205%20console"
        ),
        "currency": "AUD",
        "parser": "strict_search",
    },

    {
        "name": "BIG W Australia",
        "url": (
            "https://www.bigw.com.au/search"
            "?text=playstation%205%20console"
        ),
        "currency": "AUD",
        "parser": "strict_search",
    },
]


# ============================================================
# HEALTH REPORT
# ============================================================

source_health = []


def health(name, status, detail=""):
    source_health.append({
        "name": name,
        "status": status,
        "detail": detail,
    })


# ============================================================
# SAVED ALERTS
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
# CLEAN HTML
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
# USD -> AUD
# ============================================================

def get_usd_to_aud():

    try:

        response = requests.get(
            "https://api.frankfurter.app/latest?from=USD&to=AUD",
            timeout=15,
        )

        response.raise_for_status()

        return float(
            response.json()["rates"]["AUD"]
        )

    except Exception as exc:

        print(
            f"FX lookup failed: {exc}"
        )

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

        for match in re.findall(
            pattern,
            text,
            flags=re.I,
        ):

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
# VERIFY THAT THIS IS ACTUALLY A PS5 CONSOLE
# ============================================================

def valid_ps5_product(text):

    lower = text.lower()

    # Must identify an actual PS5.
    ps5_terms = [
        "playstation 5",
        "playstation5",
        "ps5",
    ]

    if not any(
        term in lower
        for term in ps5_terms
    ):
        return False

    # Must look like an actual console.
    console_terms = [
        "console",
        "digital edition",
        "disc console",
        "slim",
        "bundle",
    ]

    if not any(
        term in lower
        for term in console_terms
    ):
        return False

    # Reject products we don't want.
    forbidden = [
        "dualsense controller",
        "wireless controller",
        "controller only",
        "playstation portal",
        "ps portal",
        "portal remote",
        "ps5 pro",
        "playstation 5 pro",
        "disc drive",
        "vertical stand",
        "charging station",
        "charging dock",
        "headset",
        "console cover",
        "faceplate",
        "replacement shell",
        "empty box",
        "box only",
        "refurbished",
        "restored",
        "renewed",
        "pre-owned",
        "preowned",
        "used console",
        "open-box",
        "open box",
    ]

    for phrase in forbidden:

        if phrase in lower:
            return False

    return True


# ============================================================
# WALMART
# ============================================================

def parse_walmart(text):

    results = []

    lower = text.lower()

    product_markers = [
        "playstation 5 disc console slim",
        "playstation 5 digital console slim",
        "playstation5 digital edition",
        "ps5 disc console slim",
        "ps5 digital console slim",
    ]

    positions = []

    for marker in product_markers:

        start = 0

        while True:

            index = lower.find(
                marker,
                start,
            )

            if index == -1:
                break

            positions.append(index)

            start = (
                index
                + len(marker)
            )

    for index in sorted(
        set(positions)
    ):

        window = text[
            max(0, index - 80):
            min(len(text), index + 650)
        ]

        if not valid_ps5_product(
            window
        ):
            continue

        window_lower = window.lower()

        # Reject third-party/restored items.
        bad = [
            "restored",
            "refurbished",
            "open box",
            "pre-owned",
            "preowned",
        ]

        if any(
            phrase in window_lower
            for phrase in bad
        ):
            continue

        prices = money_values(
            window
        )

        if not prices:
            continue

        price = prices[0]

        edition = (
            "Digital"
            if "digital" in window_lower
            else "Disc"
        )

        results.append({
            "edition": edition,
            "price": price,
        })

    return results


# ============================================================
# BEST BUY
# ============================================================

def parse_bestbuy(text):

    results = []

    patterns = [

        (
            "Digital",
            r"PlayStation\s*5"
            r".{0,100}?"
            r"(?:Slim\s*)?"
            r"Digital"
            r".{0,500}?"
            r"\$\s*"
            r"([0-9,]+(?:\.[0-9]{1,2})?)"
        ),

        (
            "Disc",
            r"PlayStation\s*5"
            r".{0,100}?"
            r"Slim\s*Console"
            r".{0,500}?"
            r"\$\s*"
            r"([0-9,]+(?:\.[0-9]{1,2})?)"
        ),
    ]

    for edition, pattern in patterns:

        matches = re.finditer(
            pattern,
            text,
            flags=re.I | re.S,
        )

        for match in matches:

            window = text[
                max(0, match.start() - 100):
                min(len(text), match.end() + 300)
            ]

            if not valid_ps5_product(
                window
            ):
                continue

            price = parse_number(
                match.group(1)
            )

            if price is None:
                continue

            results.append({
                "edition": edition,
                "price": price,
            })

    return results


# ============================================================
# STRICT AUSTRALIAN SEARCH
# ============================================================

def parse_strict_search(text):

    results = []

    lower = text.lower()

    terms = [
        "playstation 5",
        "ps5",
    ]

    positions = []

    for term in terms:

        start = 0

        while True:

            index = lower.find(
                term,
                start,
            )

            if index == -1:
                break

            positions.append(index)

            start = (
                index
                + len(term)
            )

    for index in sorted(
        set(positions)
    ):

        window = text[
            max(0, index - 70):
            min(len(text), index + 550)
        ]

        if not valid_ps5_product(
            window
        ):
            continue

        prices = money_values(
            window
        )

        if not prices:
            continue

        window_lower = window.lower()

        edition = (
            "Digital"
            if "digital" in window_lower
            else "Disc/Standard"
        )

        results.append({
            "edition": edition,
            "price": prices[0],
        })

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
            "🎮",
        )

    return (
        None,
        "",
    )


def effective_aud(
    price,
    currency,
    usd_to_aud,
):

    if currency == "AUD":
        return price

    taxed_usd = (
        price
        * (1 + GA_SALES_TAX)
    )

    return (
        taxed_usd
        * usd_to_aud
    )


# ============================================================
# UNIQUE ALERT
# ============================================================

def deal_id(
    retailer,
    edition,
    price,
):

    raw = (
        f"{retailer}|"
        f"{edition}|"
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
    edition,
    item_price,
    currency,
    aud_total,
    classification_name,
    emoji,
    url,
    usd_to_aud,
):

    title = (
        f"PS5 {classification_name} - "
        f"A${aud_total:.0f}"
    )

    if currency == "USD":

        tax = (
            item_price
            * GA_SALES_TAX
        )

        checkout = (
            item_price
            + tax
        )

        body = (
            f"{emoji} PS5 {classification_name}\n\n"
            f"PlayStation 5 Console\n"
            f"Edition: {edition}\n"
            f"Retailer: {retailer}\n\n"
            f"Item price: US${item_price:.2f}\n"
            f"Estimated Georgia tax: US${tax:.2f}\n"
            f"Estimated checkout: US${checkout:.2f}\n"
            f"USD/AUD: {usd_to_aud:.4f}\n\n"
            f"Estimated effective cost: "
            f"A${aud_total:.2f}\n\n"
            f"Console package must include at least "
            f"the standard DualSense controller.\n\n"
            f"Tap to verify immediately."
        )

    else:

        body = (
            f"{emoji} PS5 {classification_name}\n\n"
            f"PlayStation 5 Console\n"
            f"Edition: {edition}\n"
            f"Retailer: {retailer}\n\n"
            f"Price: A${item_price:.2f}\n\n"
            f"Estimated effective cost: "
            f"A${aud_total:.2f}\n\n"
            f"Console package must include at least "
            f"the standard DualSense controller.\n\n"
            f"Tap to verify immediately."
        )

    response = requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=body.encode("utf-8"),
        headers={
            "Title": title,
            "Priority": "urgent",
            "Click": url,
            "Tags": "video_game,moneybag",
        },
        timeout=15,
    )

    response.raise_for_status()


# ============================================================
# EVALUATE DEAL
# ============================================================

def evaluate(
    retailer,
    url,
    currency,
    edition,
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

    if currency == "USD":

        print(
            f"{retailer} | "
            f"{edition} | "
            f"US${price:.2f} | "
            f"est A${aud_total:.2f}"
        )

    else:

        print(
            f"{retailer} | "
            f"{edition} | "
            f"A${price:.2f}"
        )

    if not label:
        return

    unique_id = deal_id(
        retailer,
        edition,
        price,
    )

    if unique_id in seen:

        print(
            "Already alerted."
        )

        return

    send_notification(
        retailer=retailer,
        edition=edition,
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
        "PS5 ALERT SENT"
    )


# ============================================================
# CHECK SOURCE
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
            f"BLOCKED/ERROR: {exc}"
        )

        health(
            name,
            "BLOCKED",
            str(exc),
        )

        return

    if source["parser"] == "walmart":

        results = parse_walmart(
            text
        )

    elif source["parser"] == "bestbuy":

        results = parse_bestbuy(
            text
        )

    else:

        results = parse_strict_search(
            text
        )

    if not results:

        print(
            "No verified PS5 console "
            "price found."
        )

        health(
            name,
            "NO VERIFIED PRODUCT",
            "Page loaded but no safe console+price match found",
        )

        return

    health(
        name,
        "OK",
        f"{len(results)} verified result(s)",
    )

    used = set()

    for result in results:

        combination = (
            result["edition"],
            result["price"],
        )

        if combination in used:
            continue

        used.add(
            combination
        )

        evaluate(
            retailer=name,
            url=source["url"],
            currency=source["currency"],
            edition=result["edition"],
            price=result["price"],
            usd_to_aud=usd_to_aud,
            seen=seen,
        )


# ============================================================
# HEALTH REPORT
# ============================================================

def print_health():

    print(
        "\n========================================"
    )

    print(
        "PS5 SOURCE HEALTH REPORT"
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
        "\nAmazon US: EXTERNAL TRACKER"
    )

    print(
        "Amazon AU: EXTERNAL TRACKER"
    )

    print(
        "Amazon intentionally not scraped "
        "to avoid false product matches."
    )

    print(
        "========================================"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "Starting PS5 price-error monitor..."
    )

    print(
        "\nEligible:"
    )

    print(
        "- New PS5 Slim Disc"
    )

    print(
        "- New PS5 Slim Digital"
    )

    print(
        "- Legitimate console bundles"
    )

    print(
        "- Must include at least the normal controller"
    )

    print(
        "\nExcluded:"
    )

    print(
        "- PS5 Pro"
    )

    print(
        "- Refurbished/restored/open-box"
    )

    print(
        "- Controllers/accessories alone"
    )

    print(
        "- PlayStation Portal"
    )

    print(
        "\nThresholds:"
    )

    print(
        "GOOD DEAL: <= A$700"
    )

    print(
        "GREAT DEAL: <= A$600"
    )

    print(
        "POSSIBLE PRICE ERROR: <= A$500"
    )

    print(
        "\nThere is NO minimum price."
    )

    seen = load_seen()

    usd_to_aud = (
        get_usd_to_aud()
    )

    print(
        f"\nUSD/AUD: {usd_to_aud:.4f}"
    )

    print(
        "US price includes estimated "
        "8% Georgia sales tax."
    )

    for source in SOURCES:

        check_source(
            source,
            usd_to_aud,
            seen,
        )

    print_health()

    print(
        "\nPS5 search complete."
    )


if __name__ == "__main__":
    main()
