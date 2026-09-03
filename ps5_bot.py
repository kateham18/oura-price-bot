import os
import re
import json
import html
import hashlib
import time
from pathlib import Path
from urllib.parse import urljoin

import requests


NTFY_TOPIC = os.environ["NTFY_TOPIC"]

GOOD_DEAL_AUD = 700.00
GREAT_DEAL_AUD = 600.00
PRICE_ERROR_AUD = 500.00

GA_SALES_TAX = 0.08

STATE_FILE = Path("seen_ps5_deals.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
}


# ============================================================
# SELLERS
#
# Broad seller coverage.
# Search/category pages are allowed, but alerts only happen
# when a PS5 console product block can be verified.
# ============================================================

SOURCES = [

    # ---------------- USA ----------------

    {
        "name": "Walmart US",
        "currency": "USD",
        "url": (
            "https://www.walmart.com/search"
            "?q=playstation+5+console"
        ),
    },

    {
        "name": "Target US",
        "currency": "USD",
        "url": (
            "https://www.target.com/s"
            "?searchTerm=playstation+5+console"
        ),
    },

    {
        "name": "Best Buy US",
        "currency": "USD",
        "url": (
            "https://www.bestbuy.com/site/searchpage.jsp"
            "?st=playstation+5+console"
        ),
    },

    {
        "name": "PlayStation Direct US",
        "currency": "USD",
        "url": (
            "https://direct.playstation.com/en-us/"
            "hardware/ps5"
        ),
    },

    {
        "name": "GameStop US",
        "currency": "USD",
        "url": (
            "https://www.gamestop.com/search/"
            "?q=playstation+5+console"
        ),
    },

    {
        "name": "Newegg US",
        "currency": "USD",
        "url": (
            "https://www.newegg.com/p/pl"
            "?d=playstation+5+console"
        ),
    },

    {
        "name": "B&H US",
        "currency": "USD",
        "url": (
            "https://www.bhphotovideo.com/c/search"
            "?Ntt=playstation%205%20console"
        ),
    },

    {
        "name": "Costco US",
        "currency": "USD",
        "url": (
            "https://www.costco.com/"
            "CatalogSearch?keyword=playstation+5"
        ),
    },

    {
        "name": "Sam's Club US",
        "currency": "USD",
        "url": (
            "https://www.samsclub.com/s/"
            "playstation%205%20console"
        ),
    },


    # ---------------- AUSTRALIA ----------------

    {
        "name": "JB Hi-Fi Australia",
        "currency": "AUD",
        "url": (
            "https://www.jbhifi.com.au/search"
            "?query=playstation%205%20console"
        ),
    },

    {
        "name": "Harvey Norman Australia",
        "currency": "AUD",
        "url": (
            "https://www.harveynorman.com.au/"
            "catalogsearch/result/"
            "?q=playstation+5+console"
        ),
    },

    {
        "name": "BIG W Australia",
        "currency": "AUD",
        "url": (
            "https://www.bigw.com.au/search"
            "?text=playstation%205%20console"
        ),
    },

    {
        "name": "EB Games Australia",
        "currency": "AUD",
        "url": (
            "https://www.ebgames.com.au/search"
            "?q=playstation%205%20console"
        ),
    },

    {
        "name": "Target Australia",
        "currency": "AUD",
        "url": (
            "https://www.target.com.au/search"
            "?text=playstation%205%20console"
        ),
    },

    {
        "name": "The Gamesmen Australia",
        "currency": "AUD",
        "url": (
            "https://www.gamesmen.com.au/catalogsearch/"
            "result/?q=playstation+5+console"
        ),
    },
]


DEAL_FEEDS = [
    {
        "name": "OzBargain",
        "currency": "AUD",
        "url": "https://www.ozbargain.com.au/deals/feed",
    },
]


source_health = []


# ============================================================
# HEALTH
# ============================================================

def health(name, status, detail=""):
    source_health.append({
        "name": name,
        "status": status,
        "detail": detail,
    })


# ============================================================
# STATE
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
# FETCH
# ============================================================

def fetch_raw(url):

    last_error = None

    for attempt in range(3):

        try:

            response = requests.get(
                url,
                headers=HEADERS,
                timeout=35,
                allow_redirects=True,
            )

            response.raise_for_status()

            return response.text

        except Exception as exc:

            last_error = exc

            print(
                f"Attempt {attempt + 1} failed: {exc}"
            )

            time.sleep(2 + attempt)

    raise last_error


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
# FX
# ============================================================

def get_usd_to_aud():

    try:

        response = requests.get(
            "https://api.frankfurter.app/"
            "latest?from=USD&to=AUD",
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
# MONEY
# ============================================================

def parse_number(value):

    try:
        return float(
            str(value)
            .replace(",", "")
            .replace("$", "")
            .strip()
        )

    except Exception:
        return None


def money_values(text):

    patterns = [
        r"US\$\s*([0-9,]+(?:\.[0-9]{1,2})?)",
        r"USD\s*([0-9,]+(?:\.[0-9]{1,2})?)",
        r"AU\$\s*([0-9,]+(?:\.[0-9]{1,2})?)",
        r"AUD\s*([0-9,]+(?:\.[0-9]{1,2})?)",
        r"A\$\s*([0-9,]+(?:\.[0-9]{1,2})?)",
        r"\$\s*([0-9,]+(?:\.[0-9]{1,2})?)",
    ]

    results = []

    for pattern in patterns:

        for match in re.findall(
            pattern,
            text,
            flags=re.I,
        ):

            number = parse_number(
                match
            )

            if (
                number is not None
                and number >= 1
            ):
                results.append(
                    number
                )

    return results


# ============================================================
# PRODUCT VALIDATION
# ============================================================

def is_ps5_console(title):

    lower = title.lower()

    has_ps5 = (
        "playstation 5" in lower
        or
        "playstation5" in lower
        or
        re.search(
            r"\bps5\b",
            lower,
        )
    )

    if not has_ps5:
        return False

    # We want an actual console or console bundle.
    console_clues = [
        "console",
        "digital edition",
        "disc edition",
        "disc bundle",
        "digital bundle",
        "console bundle",
        "slim bundle",
    ]

    if not any(
        clue in lower
        for clue in console_clues
    ):
        return False

    forbidden = [
        "ps5 pro",
        "playstation 5 pro",
        "playstation5 pro",

        "dualsense",
        "controller only",
        "wireless controller",
        "controller for",

        "playstation portal",
        "ps portal",

        "disc drive",
        "vertical stand",
        "charging station",
        "charging dock",
        "headset",
        "earbuds",

        "console cover",
        "faceplate",
        "skin",
        "protective cover",
        "carrying case",
        "storage case",

        "empty box",
        "box only",
        "replacement box",

        "refurbished",
        "renewed",
        "restored",
        "pre-owned",
        "preowned",
        "used console",
        "open box",
        "open-box",
    ]

    if any(
        phrase in lower
        for phrase in forbidden
    ):
        return False

    return True


def get_edition(title):

    lower = title.lower()

    if "digital" in lower:
        return "Digital"

    return "Disc/Standard"


# ============================================================
# JSON-LD PARSER
#
# Safest method where supported.
# ============================================================

def recursively_find_products(obj):

    found = []

    if isinstance(
        obj,
        dict,
    ):

        obj_type = obj.get(
            "@type"
        )

        if (
            obj_type == "Product"
            or
            (
                isinstance(obj_type, list)
                and
                "Product" in obj_type
            )
        ):
            found.append(obj)

        for value in obj.values():

            found.extend(
                recursively_find_products(
                    value
                )
            )

    elif isinstance(
        obj,
        list,
    ):

        for value in obj:

            found.extend(
                recursively_find_products(
                    value
                )
            )

    return found


def extract_jsonld_products(raw_html):

    scripts = re.findall(
        r'<script[^>]+type=["\']'
        r'application/ld\+json'
        r'["\'][^>]*>'
        r'(.*?)'
        r'</script>',
        raw_html,
        flags=re.I | re.S,
    )

    results = []

    for script in scripts:

        script = html.unescape(
            script.strip()
        )

        try:

            data = json.loads(
                script
            )

        except Exception:
            continue

        products = (
            recursively_find_products(
                data
            )
        )

        for product in products:

            name = str(
                product.get(
                    "name",
                    "",
                )
            )

            if not is_ps5_console(name):
                continue

            offers = product.get(
                "offers"
            )

            if not offers:
                continue

            if isinstance(
                offers,
                dict,
            ):
                offers = [offers]

            if not isinstance(
                offers,
                list,
            ):
                continue

            for offer in offers:

                if not isinstance(
                    offer,
                    dict,
                ):
                    continue

                raw_price = (
                    offer.get("price")
                    or
                    offer.get("lowPrice")
                )

                price = parse_number(
                    raw_price
                )

                if price is None:
                    continue

                product_url = (
                    offer.get("url")
                    or
                    product.get("url")
                )

                results.append({
                    "title": name,
                    "edition": get_edition(name),
                    "price": price,
                    "url": product_url,
                    "method": "JSON-LD",
                })

    return results


# ============================================================
# HTML FALLBACK
#
# Used when retailer doesn't expose Product JSON-LD.
# Tight windows only.
# ============================================================

def extract_html_products(raw_html):

    text = clean_text(
        raw_html
    )

    lower = text.lower()

    search_terms = [
        "playstation 5",
        "playstation5",
        "ps5 ",
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

    results = []

    for index in sorted(
        set(positions)
    ):

        window = text[
            max(0, index - 50):
            min(
                len(text),
                index + 650,
            )
        ]

        # Use beginning of card as title/context.
        title = window[:350]

        if not is_ps5_console(
            title
        ):
            continue

        prices = money_values(
            window
        )

        if not prices:
            continue

        # Never add a minimum threshold:
        # real $50/$100 pricing errors must still trigger.
        #
        # Instead reject only common accessory/payment numbers
        # when they appear as the FIRST price.
        reject_known = {
            5.99,
            9.99,
            10.00,
            14.99,
            19.99,
            29.99,
            39.99,
            49.99,
            59.99,
            69.99,
            74.99,
            79.99,
            84.99,
        }

        price = None

        for candidate in prices:

            if candidate in reject_known:
                continue

            price = candidate
            break

        if price is None:
            continue

        results.append({
            "title": title,
            "edition": get_edition(
                title
            ),
            "price": price,
            "url": None,
            "method": "HTML",
        })

    return results


# ============================================================
# DEDUPE RESULTS
# ============================================================

def dedupe_products(products):

    output = []
    seen = set()

    for product in products:

        key = (
            product["edition"],
            round(
                product["price"],
                2,
            ),
        )

        if key in seen:
            continue

        seen.add(key)

        output.append(product)

    return output


# ============================================================
# CLASSIFICATION
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

    taxed = (
        price
        * (1 + GA_SALES_TAX)
    )

    return (
        taxed
        * usd_to_aud
    )


# ============================================================
# ALERT ID
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
        raw.encode(
            "utf-8"
        )
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
    label,
    emoji,
    url,
    usd_to_aud,
):

    title = (
        f"PS5 {label} - "
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
            f"{emoji} PS5 {label}\n\n"
            f"Retailer: {retailer}\n"
            f"Edition: {edition}\n\n"
            f"Item price: US${item_price:.2f}\n"
            f"Est. Georgia tax: US${tax:.2f}\n"
            f"Est. checkout: US${checkout:.2f}\n"
            f"USD/AUD: {usd_to_aud:.4f}\n\n"
            f"Est. effective cost: "
            f"A${aud_total:.2f}\n\n"
            f"NEW PS5 console/bundle detected.\n"
            f"Tap and verify immediately."
        )

    else:

        body = (
            f"{emoji} PS5 {label}\n\n"
            f"Retailer: {retailer}\n"
            f"Edition: {edition}\n\n"
            f"Price: A${item_price:.2f}\n\n"
            f"NEW PS5 console/bundle detected.\n"
            f"Tap and verify immediately."
        )

    headers = {
        "Title": title,
        "Priority": "urgent",
        "Tags": "video_game,moneybag",
    }

    if url:
        headers["Click"] = url

    response = requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=body.encode(
            "utf-8"
        ),
        headers=headers,
        timeout=15,
    )

    response.raise_for_status()


# ============================================================
# EVALUATE
# ============================================================

def evaluate(
    retailer,
    currency,
    product,
    source_url,
    usd_to_aud,
    seen,
):

    price = product["price"]

    aud_total = effective_aud(
        price,
        currency,
        usd_to_aud,
    )

    print(
        f"{retailer} | "
        f"{product['edition']} | "
        f"{currency} {price:.2f} | "
        f"effective A${aud_total:.2f} | "
        f"{product['method']}"
    )

    label, emoji = classification(
        aud_total
    )

    if not label:
        return

    unique = deal_id(
        retailer,
        product["edition"],
        price,
    )

    if unique in seen:

        print(
            "Already alerted."
        )

        return

    product_url = (
        product.get("url")
        or
        source_url
    )

    send_notification(
        retailer=retailer,
        edition=product["edition"],
        item_price=price,
        currency=currency,
        aud_total=aud_total,
        label=label,
        emoji=emoji,
        url=product_url,
        usd_to_aud=usd_to_aud,
    )

    seen.add(
        unique
    )

    save_seen(
        seen
    )

    print(
        "ALERT SENT"
    )


# ============================================================
# CHECK RETAILER
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

        raw = fetch_raw(
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

    products = (
        extract_jsonld_products(
            raw
        )
    )

    # If no structured Product data,
    # use cautious text fallback.
    if not products:

        products = (
            extract_html_products(
                raw
            )
        )

    products = dedupe_products(
        products
    )

    if not products:

        print(
            "No verified PS5 console "
            "products found."
        )

        health(
            name,
            "NO VERIFIED PRODUCT",
            (
                "Page loaded, but no safe "
                "PS5 console + price pair found"
            ),
        )

        return

    health(
        name,
        "OK",
        f"{len(products)} verified result(s)",
    )

    for product in products:

        evaluate(
            retailer=name,
            currency=source["currency"],
            product=product,
            source_url=source["url"],
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

    url = (
        "https://www.ozbargain.com.au/"
        "deals/feed"
    )

    print(
        "\nChecking OzBargain..."
    )

    try:

        raw = fetch_raw(
            url
        )

    except Exception as exc:

        health(
            name,
            "BLOCKED",
            str(exc),
        )

        return

    items = re.findall(
        r"<item>(.*?)</item>",
        raw,
        flags=re.I | re.S,
    )

    count = 0

    for item in items:

        title_match = re.search(
            r"<title>(.*?)</title>",
            item,
            flags=re.I | re.S,
        )

        description_match = re.search(
            r"<description>(.*?)</description>",
            item,
            flags=re.I | re.S,
        )

        link_match = re.search(
            r"<link>(.*?)</link>",
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

        combined = (
            f"{title} {description}"
        )

        if not is_ps5_console(
            combined
        ):
            continue

        prices = money_values(
            combined
        )

        if not prices:
            continue

        price = prices[0]

        link = (
            clean_text(
                link_match.group(1)
            )
            if link_match
            else url
        )

        product = {
            "title": title,
            "edition": get_edition(
                title
            ),
            "price": price,
            "url": link,
            "method": "OzBargain",
        }

        count += 1

        evaluate(
            retailer=name,
            currency="AUD",
            product=product,
            source_url=link,
            usd_to_aud=usd_to_aud,
            seen=seen,
        )

    health(
        name,
        "OK",
        f"{count} relevant deal(s) found",
    )


# ============================================================
# REPORT
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
        "\nAmazon US: use external exact-product tracker"
    )

    print(
        "Amazon AU: use external exact-product tracker"
    )

    print(
        "Amazon search scraping remains disabled "
        "to prevent accessory false alerts."
    )

    print(
        "========================================"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "Starting broad PS5 deal monitor..."
    )

    print(
        "\nEligible:"
    )

    print(
        "- New PS5 Disc"
    )

    print(
        "- New PS5 Digital"
    )

    print(
        "- Console bundles"
    )

    print(
        "- At least standard included controller"
    )

    print(
        "\nExcluded:"
    )

    print(
        "- PS5 Pro"
    )

    print(
        "- Used/refurbished/open-box"
    )

    print(
        "- Controllers/accessories"
    )

    print(
        "- PlayStation Portal"
    )

    print(
        "\nThresholds:"
    )

    print(
        "GOOD <= A$700"
    )

    print(
        "GREAT <= A$600"
    )

    print(
        "PRICE ERROR <= A$500"
    )

    print(
        "\nNO LOWER PRICE LIMIT."
    )

    seen = load_seen()

    usd_to_aud = (
        get_usd_to_aud()
    )

    print(
        f"\nUSD/AUD: "
        f"{usd_to_aud:.4f}"
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

    print_health()

    print(
        "\nPS5 check complete."
    )


if __name__ == "__main__":
    main()
