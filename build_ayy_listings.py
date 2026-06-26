#!/usr/bin/env python3
"""Fetch AYY housing from domo.ayy.fi API, geocode buildings, output GeoJSON.

Building detail URLs use the ayyasunnot.fi/kustannuspaikka/{slug}/ pattern,
derived from the street address (Finnish chars mapped to ASCII, spaces → hyphens).
"""
import json, re, time, urllib.request, urllib.parse
from pathlib import Path

ROOT  = Path(__file__).resolve().parent
DATA  = ROOT / 'offline' / 'data'
OUT   = DATA / 'ayy_listings.geojson'
CACHE = DATA / 'geocode_cache.json'

# ── Helpers ─────────────────────────────────────────────
def addr_to_slug(addr):
    s = addr.lower()
    for fi, en in [('ä','a'),('ö','o'),('å','a'),('é','e'),('ü','u')]:
        s = s.replace(fi, en)
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    return re.sub(r'\s+', '-', s.strip())

def http_get(url, accept='application/json'):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64)',
        'Accept': accept,
        'X-Requested-With': 'XMLHttpRequest',
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode('utf-8')

geo = json.loads(CACHE.read_text()) if CACHE.exists() else {}

def geocode(address, city):
    key = f'{address}, {city}, Finland'
    if key in geo:
        return geo[key]
    q = urllib.parse.urlencode({'street': address, 'city': city, 'country': 'Finland',
                                'format': 'json', 'limit': 1})
    req = urllib.request.Request(
        f'https://nominatim.openstreetmap.org/search?{q}',
        headers={'User-Agent': 'AYY housing map / zhangdoudou2024@gmail.com',
                 'Referer': 'https://ayyasunnot.fi/'}
    )
    ll = None
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=12).read())
        if data:
            ll = [round(float(data[0]['lon']), 6), round(float(data[0]['lat']), 6)]
    except Exception as e:
        print(f'  geocode fail {address}, {city}: {e}')
    time.sleep(1.1)
    geo[key] = ll
    return ll

# ── Fetch apartments from Domo API ───────────────────────
print('Fetching apartments from domo.ayy.fi/apartments.json ...')
raw = json.loads(http_get('https://domo.ayy.fi/apartments.json'))
apts = raw['apartments']
print(f'  {len(apts)} apartments')

# ── Aggregate by building ────────────────────────────────
buildings = {}
for a in apts:
    b   = a['building']
    bid = b['id']
    if bid not in buildings:
        buildings[bid] = {
            'street_address': b['street_address'],
            'city':           b['city'] or 'Finland',
            'building_year':  b.get('building_year'),
            'rents': [], 'plan_types': set(),
        }
    if a.get('rent_cents'):
        buildings[bid]['rents'].append(a['rent_cents'])
    if a.get('plan_type'):
        buildings[bid]['plan_types'].add(a['plan_type'])

# ── Geocode & build GeoJSON ──────────────────────────────
plan_map = {'yksio':'studio/1h','kaksio':'2h','kolmio':'3h',
            'solu':'solu','nelio':'4h','viisio':'5h'}

features = []
for bid, b in sorted(buildings.items()):
    addr = b['street_address']
    city = b['city']
    print(f'Geocoding: {addr}, {city}')
    ll = geocode(addr, city)
    if not ll:
        ll = geocode(addr, 'Finland')
    if not ll:
        print(f'  SKIP: no coords for {addr}')
        continue

    rents = b['rents']
    rent_str = None
    if rents:
        lo, hi = min(rents) // 100, max(rents) // 100
        rent_str = f'€{lo}' if lo == hi else f'€{lo}–{hi}'

    types = sorted(plan_map.get(t, t) for t in b['plan_types'])
    slug  = addr_to_slug(addr)
    n_units = sum(1 for a in apts if a['building']['id'] == bid)

    features.append({
        'type': 'Feature',
        'properties': {
            'address':    addr,
            'city':       city,
            'rent':       rent_str,
            'room_types': ', '.join(types) if types else None,
            'year_built': b['building_year'],
            'url':        f'https://ayyasunnot.fi/kustannuspaikka/{slug}/',
            'n_units':    n_units,
        },
        'geometry': {'type': 'Point', 'coordinates': ll}
    })
    print(f'  OK → {ll}  rent={rent_str}  {n_units} units')

# ── Save ─────────────────────────────────────────────────
CACHE.write_text(json.dumps(geo, ensure_ascii=False), encoding='utf-8')
fc = {'type': 'FeatureCollection', 'features': features}
OUT.write_text(json.dumps(fc, ensure_ascii=False), encoding='utf-8')
print(f'\nSaved {len(features)}/{len(buildings)} buildings → {OUT}')
