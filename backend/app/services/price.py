"""Product price extraction for price-watch automations.

Tries, in order of reliability: schema.org JSON-LD offers, price meta tags /
microdata, then a currency-pattern heuristic (reported as low confidence).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup

_CURRENCY_RE = re.compile(
    r"(?P<cur>₹|Rs\.?|INR|\$|USD|€|EUR|£|GBP)\s?(?P<num>\d{1,3}(?:[,\s]\d{2,3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
_SYMBOL_TO_CODE = {"₹": "INR", "rs": "INR", "rs.": "INR", "inr": "INR", "$": "USD", "usd": "USD", "€": "EUR",
                   "eur": "EUR", "£": "GBP", "gbp": "GBP"}


@dataclass
class PriceInfo:
    price: float
    currency: str | None
    method: str
    confidence: str  # high | medium | low
    title: str | None = None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    s = re.sub(r"[^\d.]", "", str(value).replace(",", ""))
    try:
        return float(s) if s else None
    except ValueError:
        return None


def _walk_jsonld(node: Any):
    if isinstance(node, list):
        for item in node:
            yield from _walk_jsonld(item)
    elif isinstance(node, dict):
        yield node
        for key in ("@graph", "offers", "mainEntity", "itemListElement"):
            if key in node:
                yield from _walk_jsonld(node[key])


def extract_price(html: str) -> PriceInfo | None:
    soup = BeautifulSoup(html, "lxml")
    title = None
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    elif soup.title and soup.title.string:
        title = soup.title.string.strip()

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _walk_jsonld(data):
            types = node.get("@type")
            types = types if isinstance(types, list) else [types]
            if any(t in ("Offer", "AggregateOffer") for t in types):
                price = _to_float(node.get("price") or node.get("lowPrice"))
                if price:
                    name = title
                    return PriceInfo(price, node.get("priceCurrency"), "json-ld", "high", name)

    for attrs in ({"property": "product:price:amount"}, {"property": "og:price:amount"}, {"itemprop": "price"}):
        tag = soup.find(attrs=attrs)
        if tag is not None:
            price = _to_float(tag.get("content") or tag.get_text())
            if price:
                cur_tag = soup.find(attrs={"property": "product:price:currency"}) or soup.find(
                    attrs={"itemprop": "priceCurrency"})
                currency = cur_tag.get("content") if cur_tag is not None else None
                return PriceInfo(price, currency, "meta", "medium", title)

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)[:200000]
    m = _CURRENCY_RE.search(text)
    if m:
        price = _to_float(m.group("num"))
        if price:
            return PriceInfo(price, _SYMBOL_TO_CODE.get(m.group("cur").lower()), "text-pattern", "low", title)
    return None
