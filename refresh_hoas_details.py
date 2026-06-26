#!/usr/bin/env python3
"""Refresh HOAS rent, condition, and year fields without recomputing commute data.

Fetched pages are cached under offline/data/hoas_page_cache/ so re-runs
only hit the network for URLs that haven't been cached yet.
"""
import json
import hashlib
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from hoas_page_parser import parse_housing_page


ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'offline' / 'data'
CACHE_DIR = DATA / 'hoas_page_cache'
CACHE_DIR.mkdir(exist_ok=True)
SOURCES = (
    DATA / 'hoas_listings.geojson',
    DATA / 'hoas_listings_aalto_otaniemi.geojson',
)


def _cache_path(url: str) -> Path:
    key = hashlib.sha1(url.encode()).hexdigest()
    return CACHE_DIR / (key + '.html')

def get(url, force=False):
    cp = _cache_path(url)
    if not force and cp.exists():
        return cp.read_text(encoding='utf-8', errors='replace')
    result = subprocess.run(
        ['timeout', '-s', 'KILL', '-k', '2', '30', 'curl', '-4', '-sS', '-L', '--fail', '--connect-timeout', '8', '--max-time', '25',
         '-A', 'Mozilla/5.0 (compatible; offline-map-builder)', url],
        check=True, capture_output=True, timeout=35,
    )
    html = result.stdout.decode('utf-8', errors='replace')
    cp.write_text(html, encoding='utf-8')
    return html


def main():
    datasets = [(path, json.loads(path.read_text(encoding='utf-8'))) for path in SOURCES]
    by_url = {}
    for _, dataset in datasets:
        for feature in dataset.get('features', []):
            url = feature.get('properties', {}).get('url')
            if url:
                by_url.setdefault(url, []).append(feature)

    # The existing map already has the desired building universe. Refresh those
    # URLs directly so a sitemap outage cannot prevent a price refresh.
    urls = sorted(by_url)
    updated = failed = missing_price = missing_condition = 0
    def fetch(url):
        try:
            return url, parse_housing_page(get(url)), None
        except Exception as error:
            return url, None, error

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(fetch, url) for url in urls]
        for number, future in enumerate(as_completed(futures), 1):
            url, details, error = future.result()
            if error is not None:
                failed += 1
                print(f'[{number}/{len(urls)}] failed: {url} ({error})')
                continue
            for feature in by_url[url]:
                props = feature.setdefault('properties', {})
                if details['address']:
                    props['address'] = details['address']
                props['min_rent'] = details['min_rent']
                props['max_rent'] = details['max_rent']
                props['condition'] = details['condition']
                props['year_built'] = details['year_built']
                props['year_renovated'] = details['year_renovated']
            updated += 1
            missing_price += details['min_rent'] is None
            missing_condition += details['condition'] is None
            if number % 20 == 0 or number == len(urls):
                print(f'[{number}/{len(urls)}] updated={updated} failed={failed} '
                      f'no_price={missing_price} no_condition={missing_condition}')

    for path, dataset in datasets:
        path.write_text(json.dumps(dataset, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'Finished: updated={updated}, failed={failed}, no_price={missing_price}, '
          f'no_condition={missing_condition}')


if __name__ == '__main__':
    main()
