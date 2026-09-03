import hashlib
import json
import os
from pathlib import Path

import requests

from safe_tracker import scan_source

NTFY_TOPIC = os.environ["NTFY_TOPIC"]

STATE_FILE = Path("seen_deals.json")

GOOD_DEAL_AUD = 650.00
GREAT_DEAL_AUD = 600.00
PRICE_ERROR_AUD = 550.00

GA_SALES_TAX = 0.08


TARGET_GOLD = [
    "https://www.target.com/p/-/A-95006350",
    "https://www.target.com/p/-/A-95006341",
    "https://www.target.com/p/-/A-95006370",
    "https://www.target.com/p/-/A-95006360",
    "https://www.target.com/p/-/A-95006380",
    "https://www.target.com/p/-/A-95006355",
    "https://www.target.com/p/-/A-95006381",
    "https://www.target.com/p/-/A-95006326",
]


SOURCES = [
    {
        "name": "Oura US",
        "currency": "USD",
        "url": "https://ouraring.com/store/rings/oura-ring-5",
    },
    {
        "name": "Target US",
        "currency": "USD",
        "url": "https://www.target.com/s?searchTerm=oura+ring+5+gold",
        "seed_urls": TARGET_GOLD,
    },
    {
        "name": "Walmart US",
        "currency": "USD",
        "url": "https://www.walmart.com/search?q=oura+ring+5+gold",
        "seed_urls": [
            "https://www.walmart.com/ip/19953755891"
        ],
    },
    {
        "name": "Best Buy US",
        "currency": "USD",
        "url": "https://www.bestbuy.com/site/searchpage.jsp?st=oura+ring+5+gold",
    },
    {
        "name": "Costco US",
        "currency": "USD",
        "url": "https://www.costco.com/CatalogSearch?keyword=oura+ring+5+gold",
        "seed_urls": [
            "https://www.costco.com/p/-/oura-ring-5-gold-smart-ring-exclusive-bundle-ring-additional-charger-additional-year-of-manufacturers-warranty/4201004522"
        ],
    },
    {
        "name": "Sam's Club US",
        "currency": "USD",
        "url": "https://www.samsclub.com/s/oura%20ring%205%20gold",
        "seed_urls": [
            "https://www.samsclub.com/ip/Oura-Ring-5/20353851114"
        ],
    },
    {
        "name": "Amazon US",
        "currency": "USD",
        "url": "https://www.amazon.com/s?k=Oura+Ring+5+Gold",
    },

    {
        "name": "JB Hi-Fi Australia",
        "currency": "AUD",
        "url": "https://www.jbhifi.com.au/search?query=oura%20ring%205%20gold",
    },
    {
        "name": "Harvey Norman Australia",
        "currency": "AUD",
        "url": "https://www.harveynorman.com.au/catalogsearch/result/?q=oura+ring+5+gold",
    },
    {
        "name": "Amazon Australia",
        "currency": "AUD",
        "url": "https://www.amazon.com.au/s?k=Oura+Ring+5+Gold",
    },
]


FORBIDDEN = [
    "sizing kit",
    "charger",
    "charging case",
    "replacement charger",
    "ring protector",
    "silicone cover",
    "protective cover",
    "case for oura",
    "oura ring 4",
    "gen3",
    "generation 3",
]


def product_validator(title):
    lower = (
        title or ""
    ).lower()

    if (
        "oura" not in lower
        or "ring 5" not in lower
        or "gold" not in lower
    ):
        return False

    if any(
        x in lower
        for x in FORBIDDEN
    ):
        return False

    return True


def discovery_validator(text):
    lower = (
        text or ""
    ).lower()

    if any(
        x in lower
        for x in FORBIDDEN
    ):
        return False

    return (
        "oura" in lower
        and (
            "ring-5" in lower
            or "ring 5" in lower
        )
        and "gold" in lower
    )


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


def fx_rate():
    try:
        r = requests.get(
            "https://api.frankfurter.app/latest?from=USD&to=AUD",
            timeout=15,
        )

        r.raise_for_status()

        return float(
            r.json()["rates"]["AUD"]
        )

    except Exception:
        return 1.40


def aud_cost(
    price,
    currency,
    fx,
):
    if currency == "AUD":
        return price

    return (
        price
        * (1 + GA_SALES_TAX)
        * fx
    )


def classify(cost):
    if cost <= PRICE_ERROR_AUD:
        return (
            "POSSIBLE PRICE ERROR",
            "🚨",
        )

    if cost <= GREAT_DEAL_AUD:
        return (
            "GREAT DEAL",
            "🔥",
        )

    if cost <= GOOD_DEAL_AUD:
        return (
            "GOOD DEAL",
            "💍",
        )

    return (
        None,
        "",
    )


def fingerprint(
    retailer,
    seller,
    title,
    price,
):
    raw = (
        f"{retailer}|"
        f"{seller}|"
        f"{title}|"
        f"{price:.2f}"
    )

    return hashlib.sha256(
        raw.encode()
    ).hexdigest()


def send_alert(
    retailer,
    seller,
    row,
    currency,
    cost,
    label,
    emoji,
    fx,
):
    price = float(
        row["price"]
    )

    seller_line = (
        f"Seller: {seller}\n"
        if seller
        else ""
    )

    if currency == "USD":
        taxed = (
            price
            * (1 + GA_SALES_TAX)
        )

        body = (
            f"{emoji} {label}\n\n"
            f"Gold Oura Ring 5\n"
            f"Retailer: {retailer}\n"
            f"{seller_line}"
            f"Product: {row['title']}\n\n"
            f"Item price: US${price:.2f}\n"
            f"Est. Georgia checkout: US${taxed:.2f}\n"
            f"USD/AUD: {fx:.4f}\n"
            f"Est. effective cost: A${cost:.2f}\n\n"
            f"Tap to verify immediately."
        )

    else:
        body = (
            f"{emoji} {label}\n\n"
            f"Gold Oura Ring 5\n"
            f"Retailer: {retailer}\n"
            f"{seller_line}"
            f"Product: {row['title']}\n\n"
            f"Price: A${price:.2f}\n\n"
            f"Tap to verify immediately."
        )

    headers = {
        "Title": (
            f"{label} - "
            f"A${cost:.0f}"
        ),
        "Priority": "urgent",
        "Tags": "ring,moneybag",
    }

    if row.get("url"):
        headers["Click"] = row["url"]

    r = requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=body.encode("utf-8"),
        headers=headers,
        timeout=15,
    )

    r.raise_for_status()


def main():
    print(
        "Starting SAFE Gold Oura Ring 5 monitor"
    )

    print(
        "Only structured Product prices are accepted."
    )

    print(
        "Search-page dollar amounts are never used."
    )

    print(
        "There is NO minimum price: "
        "a verified A$20 Gold Ring 5 would still alert."
    )

    fx = fx_rate()
    seen = load_seen()
    health = []

    for source in SOURCES:
        name = source["name"]

        print(
            f"\nChecking {name}..."
        )

        try:
            rows, links = scan_source(
                source,
                product_validator,
                discovery_validator,
                max_links=12,
                workers=6,
            )

        except Exception as exc:
            health.append(
                (
                    "BLOCKED",
                    name,
                    str(exc),
                )
            )

            print(
                f"BLOCKED | {exc}"
            )

            continue

        safe_rows = [
            r
            for r in rows
            if product_validator(
                r.get(
                    "title",
                    "",
                )
            )
        ]

        if not safe_rows:
            health.append(
                (
                    "NO VERIFIED PRODUCT",
                    name,
                    (
                        f"{links} candidate link(s), "
                        f"0 structured price matches"
                    ),
                )
            )

            print(
                "No verified Gold Ring 5 + "
                "structured-price result."
            )

            continue

        health.append(
            (
                "OK",
                name,
                (
                    f"{len(safe_rows)} "
                    f"verified product(s)"
                ),
            )
        )

        for row in safe_rows:
            price = float(
                row["price"]
            )

            seller = (
                row.get("seller")
                or ""
            )

            cost = aud_cost(
                price,
                source["currency"],
                fx,
            )

            print(
                f"{row['title']} | "
                f"{seller or 'seller not exposed'} | "
                f"{source['currency']} "
                f"{price:.2f} | "
                f"A${cost:.2f}"
            )

            label, emoji = classify(
                cost
            )

            if not label:
                continue

            key = fingerprint(
                name,
                seller,
                row["title"],
                price,
            )

            if key in seen:
                continue

            send_alert(
                name,
                seller,
                row,
                source["currency"],
                cost,
                label,
                emoji,
                fx,
            )

            seen.add(key)

            save_seen(
                seen
            )

            print(
                "ALERT SENT"
            )

    print(
        "\n========================================"
    )

    print(
        "OURA SOURCE HEALTH REPORT"
    )

    print(
        "========================================"
    )

    for status, name, detail in health:
        print(
            f"{status} | {name}"
        )

        print(
            f"  {detail}"
        )

    print(
        "========================================"
    )


if __name__ == "__main__":
    main()
