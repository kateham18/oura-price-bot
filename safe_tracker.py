import html as html_lib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def fetch(url, timeout=18, attempts=2):
    last = None
    for attempt in range(attempts):
        try:
            r = requests.get(
                url,
                headers=HEADERS,
                timeout=timeout,
                allow_redirects=True,
            )
            r.raise_for_status()
            return r.text, r.url
        except Exception as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    raise last


def parse_number(value):
    if value is None:
        return None
    try:
        s = str(value).replace(",", "").replace("$", "").strip()
        return float(s)
    except Exception:
        return None


def _walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _as_types(obj):
    t = obj.get("@type") if isinstance(obj, dict) else None
    if isinstance(t, list):
        return {str(x).lower() for x in t}
    if t is None:
        return set()
    return {str(t).lower()}


def _extract_offer_rows(offers):
    if not offers:
        return []

    if isinstance(offers, list):
        out = []
        for o in offers:
            out.extend(_extract_offer_rows(o))
        return out

    if not isinstance(offers, dict):
        return []

    rows = []
    types = _as_types(offers)

    if "aggregateoffer" in types:
        for key in ("lowPrice", "price"):
            p = parse_number(offers.get(key))
            if p is not None:
                rows.append({
                    "price": p,
                    "seller": None,
                    "condition": str(offers.get("itemCondition", "")),
                    "availability": str(offers.get("availability", "")),
                    "url": offers.get("url"),
                })
                break

        nested = offers.get("offers")
        if nested:
            rows.extend(_extract_offer_rows(nested))

        return rows

    p = parse_number(offers.get("price"))

    if p is None:
        p = parse_number(offers.get("lowPrice"))

    if p is None:
        return []

    seller = offers.get("seller")

    if isinstance(seller, dict):
        seller = seller.get("name")

    rows.append({
        "price": p,
        "seller": str(seller) if seller else None,
        "condition": str(offers.get("itemCondition", "")),
        "availability": str(offers.get("availability", "")),
        "url": offers.get("url"),
    })

    return rows


def structured_products(raw_html, base_url, validator):
    soup = BeautifulSoup(raw_html, "html.parser")
    results = []

    scripts = soup.find_all(
        "script",
        attrs={
            "type": re.compile(r"application/ld\+json", re.I)
        },
    )

    for script in scripts:
        content = script.string or script.get_text() or ""

        if not content.strip():
            continue

        try:
            data = json.loads(
                html_lib.unescape(content.strip())
            )
        except Exception:
            continue

        for node in _walk(data):
            if "product" not in _as_types(node):
                continue

            name = str(
                node.get("name", "")
            ).strip()

            if not validator(name):
                continue

            for offer in _extract_offer_rows(
                node.get("offers")
            ):
                url = (
                    offer.get("url")
                    or node.get("url")
                    or base_url
                )

                if url:
                    url = urljoin(
                        base_url,
                        str(url),
                    )

                results.append({
                    "title": name,
                    "price": offer["price"],
                    "seller": offer.get("seller"),
                    "condition": offer.get("condition", ""),
                    "availability": offer.get("availability", ""),
                    "url": url,
                    "method": "JSON-LD",
                })

    return results


def meta_product(raw_html, base_url, validator):
    soup = BeautifulSoup(raw_html, "html.parser")

    title = ""

    for selector, attr in [
        ('meta[property="og:title"]', "content"),
        ('meta[name="twitter:title"]', "content"),
    ]:
        tag = soup.select_one(selector)

        if tag and tag.get(attr):
            title = tag.get(attr).strip()
            break

    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(" ", strip=True)

    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)

    if not validator(title):
        return []

    price = None

    selectors = [
        'meta[property="product:price:amount"]',
        'meta[itemprop="price"]',
        '[itemprop="price"][content]',
    ]

    for selector in selectors:
        tag = soup.select_one(selector)

        if tag:
            candidate = (
                tag.get("content")
                or tag.get("value")
            )

            price = parse_number(candidate)

            if price is not None:
                break

    if price is None:
        return []

    canonical = soup.find(
        "link",
        rel="canonical",
    )

    url = (
        canonical.get("href")
        if canonical and canonical.get("href")
        else base_url
    )

    return [{
        "title": title,
        "price": price,
        "seller": None,
        "condition": "",
        "availability": "",
        "url": urljoin(base_url, url),
        "method": "META",
    }]


def discover_links(
    raw_html,
    base_url,
    discovery_validator,
    max_links=8,
):
    soup = BeautifulSoup(
        raw_html,
        "html.parser",
    )

    base_host = (
        urlparse(base_url)
        .netloc.lower()
        .removeprefix("www.")
    )

    links = []
    seen = set()

    for a in soup.find_all(
        "a",
        href=True,
    ):
        text = a.get_text(
            " ",
            strip=True,
        )

        href = html_lib.unescape(
            a.get("href", "")
        ).strip()

        if not href:
            continue

        full = urljoin(
            base_url,
            href,
        )

        full, _ = urldefrag(full)

        host = (
            urlparse(full)
            .netloc.lower()
            .removeprefix("www.")
        )

        if host and base_host and not (
            host == base_host
            or host.endswith("." + base_host)
            or base_host.endswith("." + host)
        ):
            continue

        haystack = f"{text} {href}"

        if not discovery_validator(
            haystack
        ):
            continue

        if full in seen:
            continue

        seen.add(full)
        links.append(full)

        if len(links) >= max_links:
            break

    return links


def verify_product_url(
    url,
    validator,
):
    raw, final_url = fetch(url)

    rows = structured_products(
        raw,
        final_url,
        validator,
    )

    if not rows:
        rows = meta_product(
            raw,
            final_url,
            validator,
        )

    return rows


def scan_source(
    source,
    product_validator,
    discovery_validator,
    max_links=8,
    workers=6,
):
    raw, final_url = fetch(
        source["url"]
    )

    results = structured_products(
        raw,
        final_url,
        product_validator,
    )

    links = discover_links(
        raw,
        final_url,
        discovery_validator,
        max_links=max_links,
    )

    for seed in source.get(
        "seed_urls",
        [],
    ):
        if seed not in links:
            links.append(seed)

    links = links[:max_links]

    if links:
        with ThreadPoolExecutor(
            max_workers=min(
                workers,
                len(links),
            )
        ) as pool:

            futures = {
                pool.submit(
                    verify_product_url,
                    link,
                    product_validator,
                ): link
                for link in links
            }

            for fut in as_completed(
                futures
            ):
                try:
                    results.extend(
                        fut.result()
                    )
                except Exception:
                    pass

    deduped = []
    seen = set()

    for row in results:
        key = (
            re.sub(
                r"\s+",
                " ",
                row.get(
                    "title",
                    "",
                ).lower(),
            ).strip(),
            round(
                float(row["price"]),
                2,
            ),
            row.get("seller") or "",
            row.get("url") or "",
        )

        if key in seen:
            continue

        seen.add(key)
        deduped.append(row)

    return deduped, len(links)
