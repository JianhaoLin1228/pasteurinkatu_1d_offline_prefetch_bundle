"""Extract display-safe HOAS building details from an individual page.

HOAS pages include many euro amounts that are not rent (fees, deposits, and
other UI values). This module accepts prices only when an explicit rent label
is adjacent to the amount. Unknown markup deliberately yields ``None`` rather
than a misleading range.
"""
from __future__ import annotations

import html
import re


_TAG_RE = re.compile(r'<[^>]+>')
_SPACE_RE = re.compile(r'\s+')
_RENT_LABEL_RE = re.compile(
    r'(?is)\b(?:monthly\s+rent|rent|vuokra)\b.{0,100}?'
    r'(\d{3,4})\s*€(?:\s*(?:/\s*(?:month|kk)|per\s+month))?'
    r'(?:\s*(?:[-–—]|to)\s*(\d{3,4})\s*€)?'
)
_RENT_RANGE_RE = re.compile(
    r'(?is)\b(?:monthly\s+rent|rent|vuokra)\b.{0,100}?'
    r'(\d{3,4})\s*(?:[-–—]|to)\s*(\d{3,4})\s*€'
)
_APARTMENT_RENT_RE = re.compile(
    r'(?is)<div[^>]+class=["\'][^"\']*\brent\b[^"\']*["\'][^>]*>\s*(\d{3,4})\s*€\s*</div>'
)
_CONDITION_RE = re.compile(
    r'(?is)\b(?:housing\s+condition|condition|kunto)\b\s*[:\-]?\s*'
    r'(good|satisfactory|renovated|new|excellent|fair)\b'
)
# Match "Construction year" or "renovation year" label followed by year(s) like 1979 or 1997, 2020
_YEAR_LABEL_RE = re.compile(
    r'(?is)(?P<label>construction\s+year|renovation\s+year)\s{1,200}(?P<years>(?:(?:19|20)\d{2}[\s,/]*)+)'
)


def text_content(page: str) -> str:
    page = re.sub(r'(?is)<(?:script|style)[^>]*>.*?</(?:script|style)>', ' ', page)
    page = html.unescape(_TAG_RE.sub(' ', page))
    return _SPACE_RE.sub(' ', page).strip()


def parse_housing_page(page: str) -> dict[str, object | None]:
    """Return address, labelled rent range, and the advertised condition."""
    title = re.search(r'(?is)<h1[^>]*>(.*?)</h1>', page)
    if not title:
        title = re.search(r'(?is)<title>(.*?)\s*-\s*Hoas', page)
    address = text_content(title.group(1)) if title else None

    text = text_content(page)
    # HOAS's current building page renders each actual apartment price in a
    # ``<div class="rent">``. Prefer those values; they exclude summary cards,
    # deposits, and unrelated site-wide euro amounts.
    rents = [int(value) for value in _APARTMENT_RENT_RE.findall(page)]
    if not rents:
        rents = []
        for match in _RENT_LABEL_RE.finditer(text):
            rents.append(int(match.group(1)))
            if match.group(2):
                rents.append(int(match.group(2)))
        for match in _RENT_RANGE_RE.finditer(text):
            rents.extend((int(match.group(1)), int(match.group(2))))
    rents = [rent for rent in rents if 150 <= rent <= 2500]

    condition = None
    match = _CONDITION_RE.search(text)
    if match:
        condition = match.group(1).title()

    year_built = None
    year_renovated = []
    for m in _YEAR_LABEL_RE.finditer(text):
        years = [int(y) for y in re.findall(r'(?:19|20)\d{2}', m.group('years'))]
        if 'construction' in m.group('label').lower():
            year_built = years[0] if years else None
        else:
            year_renovated.extend(years)

    return {
        'address': address,
        'min_rent': min(rents) if rents else None,
        'max_rent': max(rents) if rents else None,
        'condition': condition,
        'year_built': year_built,
        'year_renovated': sorted(set(year_renovated)) if year_renovated else None,
    }
