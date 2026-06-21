#!/usr/bin/env python3
"""Scrape AYY housing listings from ayyasunnot.fi and geocode them."""
import json, re, time, urllib.request, urllib.parse
from pathlib import Path

ROOT   = Path(__file__).resolve().parent
DATA   = ROOT / 'offline' / 'data'
OUT    = DATA / 'ayy_listings.geojson'
CACHE  = DATA / 'geocode_cache.json'

UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'

def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode('utf-8', errors='replace')

# ── Load geocode cache ──────────────────────────────────
geo = json.loads(CACHE.read_text()) if CACHE.exists() else {}

def geocode(address, city='Finland'):
    key = f'{address}, {city}'
    if key in geo:
        return geo[key]
    q = f'{address}, {city}'
    params = urllib.parse.urlencode({
        'q': q, 'format': 'json', 'limit': 1,
        'countrycodes': 'fi',
        'viewbox': '24.40,60.50,25.55,60.05', 'bounded': 0,
    })
    try:
        res = json.loads(get('https://nominatim.openstreetmap.org/search?' + params))
        ll = [round(float(res[0]['lon']),6), round(float(res[0]['lat']),6)] if res else None
    except Exception as e:
        print(f'  geocode fail {q}: {e}')
        ll = None
    time.sleep(1.2)
    geo[key] = ll
    return ll

# ── Scrape all pages ────────────────────────────────────
BASE = 'https://ayyasunnot.fi'
buildings = []
page = 1
while True:
    url = f'{BASE}/asuntohaku/?page={page}'
    print(f'Fetching page {page}: {url}')
    html = get(url)
    
    # Extract building cards: /kustannuspaikka/slug/
    cards = re.findall(
        r'href=["\']({}/kustannuspaikka/[^"\']+)["\'].*?'
        r'(?:Etu-Töölö|Jätkäsaari|Puotila|Teekkarikylä|Arabianranta|Herttoniemi|'
        r'Kallio|Leppävaara|Otaniemi|Patola|Pitäjänmäki|Roihuvuori|Taka-Töölö|Vuosaari|[A-ZÄÖÅ][a-zäöå\-]+)'
        r'.*?</a>'.format(BASE),
        html, re.S
    )
    
    # Simpler: just get all /kustannuspaikka/ links
    slugs = re.findall(r'href=["\']({}/kustannuspaikka/([^"\']+))["\']'.format(BASE), html)
    seen_urls = set()
    for full_url, slug in slugs:
        if full_url not in seen_urls:
            seen_urls.add(full_url)
            buildings.append({'url': full_url, 'slug': slug.strip('/')})
    
    # Check if there's a next page
    if f'page={page+1}' in html or f'page={page + 1}' in html:
        page += 1
        time.sleep(0.5)
    else:
        # Check pagination text
        m = re.search(r'/\s*(\d+)\s*</[a-z]+>\s*(?:Seuraava|Next|›)', html)
        total_pages = int(m.group(1)) if m else page
        if page < total_pages:
            page += 1
            time.sleep(0.5)
        else:
            break

print(f'Found {len(buildings)} buildings total')

# ── Fetch each building page for details ────────────────
features = []
for b in buildings:
    slug = b['slug']
    url  = b['url']
    print(f'  Fetching {slug}...')
    try:
        html = get(url)
        time.sleep(0.3)
    except Exception as e:
        print(f'    FAIL: {e}')
        continue
    
    # Extract address from slug (e.g. jamerantaival-1 → Jämeräntaival 1)
    # Also try to extract from page content
    addr_from_page = None
    
    # Try h1 or address fields
    m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
    if m:
        addr_from_page = re.sub(r'<[^>]+>', '', m.group(1)).strip()
    
    # Extract neighborhood
    neighborhood = None
    m = re.search(r'(?:kaupunginosa|Kaupunginosa|area)[^>]*>([^<]+)<', html, re.I)
    if m:
        neighborhood = m.group(1).strip()
    
    # Extract rent range
    rent = None
    m = re.search(r'(\d[\d\s,\.]+)\s*[–\-]\s*(\d[\d\s,\.]+)\s*€/kk', html)
    if m:
        rent = f'{m.group(1).strip()}–{m.group(2).strip()} €/kk'
    else:
        m = re.search(r'(\d[\d\s,\.]+)\s*€/kk', html)
        if m:
            rent = f'{m.group(1).strip()} €/kk'
    
    # Extract room types
    rooms = re.findall(r'\b(Solu|1h|2h|3h|4h|[Ss]tudio)\b', html)
    room_types = ', '.join(sorted(set(rooms))) if rooms else None
    
    # Build address from slug
    slug_clean = slug.replace('-', ' ')
    m = re.match(r'([a-zäöåA-ZÄÖÅ\s]+?)\s+(\d+[a-z]?)$', slug_clean)
    if m:
        street = m.group(1).title()
        num    = m.group(2)
        addr   = f'{street} {num}'
    else:
        addr = addr_from_page or slug_clean.title()
    
    # Geocode
    # Try common Finnish city names
    ll = None
    for city in ['Espoo, Finland', 'Helsinki, Finland', 'Vantaa, Finland', 'Finland']:
        ll = geocode(addr, city.replace(', Finland', '').strip() if ', ' in city else city)
        if ll:
            break
    
    if not ll:
        print(f'    No coords for {addr}')
        continue
    
    props = {
        'address':      addr,
        'neighborhood': neighborhood,
        'rent':         rent,
        'room_types':   room_types,
        'url':          url,
    }
    features.append({
        'type': 'Feature',
        'properties': {k: v for k, v in props.items() if v is not None},
        'geometry': {'type': 'Point', 'coordinates': ll}
    })
    print(f'    OK: {addr} → {ll}, rent={rent}')

# ── Save ────────────────────────────────────────────────
CACHE.write_text(json.dumps(geo, ensure_ascii=False, indent=None), encoding='utf-8')
fc = {'type': 'FeatureCollection', 'features': features}
OUT.write_text(json.dumps(fc, ensure_ascii=False), encoding='utf-8')
print(f'\nSaved {len(features)} AYY buildings to {OUT}')
