#!/usr/bin/env python3
"""Fetch K-group, S-group and Lidl supermarkets in Helsinki metro from Overpass API."""
import json, time, urllib.request, urllib.parse
from pathlib import Path

OUT = Path(__file__).resolve().parent / 'offline' / 'data'

BBOX = '59.9,24.4,60.45,25.6'   # lat_min,lon_min,lat_max,lon_max

CHAINS = {
    'k': {
        'name_re': r'K-Market|K-Supermarket|K-Citymarket|K-Extra',
        'file': 'supermarkets_k.geojson',
    },
    's': {
        'name_re': r'S-market|Prisma|Sale|Alepa|ABC',
        'file': 'supermarkets_s.geojson',
    },
    'lidl': {
        'name_re': r'Lidl',
        'file': 'supermarkets_lidl.geojson',
    },
}

OVERPASS = 'https://overpass-api.de/api/interpreter'

def query(name_re):
    q = f"""
[out:json][timeout:30];
(
  node["shop"="supermarket"]["name"~"{name_re}",i]({BBOX});
  way["shop"="supermarket"]["name"~"{name_re}",i]({BBOX});
  node["shop"="convenience"]["name"~"{name_re}",i]({BBOX});
  way["shop"="convenience"]["name"~"{name_re}",i]({BBOX});
);
out center;
"""
    data = urllib.parse.urlencode({'data': q}).encode()
    req = urllib.request.Request(OVERPASS, data=data,
          headers={'User-Agent': 'Helsinki supermarket map / zhangdoudou2024@gmail.com'})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read())

def to_geojson(elements):
    features = []
    for e in elements:
        if e['type'] == 'node':
            lat, lon = e['lat'], e['lon']
        elif e['type'] == 'way' and 'center' in e:
            lat, lon = e['center']['lat'], e['center']['lon']
        else:
            continue
        tags = e.get('tags', {})
        features.append({
            'type': 'Feature',
            'properties': {
                'name':    tags.get('name', ''),
                'address': tags.get('addr:street', '') + (' ' + tags.get('addr:housenumber', '')).rstrip(),
                'opening_hours': tags.get('opening_hours', ''),
            },
            'geometry': {'type': 'Point', 'coordinates': [round(lon, 6), round(lat, 6)]}
        })
    return {'type': 'FeatureCollection', 'features': features}

for key, cfg in CHAINS.items():
    print(f'Fetching {key} ...')
    raw = query(cfg['name_re'])
    fc = to_geojson(raw['elements'])
    out_path = OUT / cfg['file']
    out_path.write_text(json.dumps(fc, ensure_ascii=False), encoding='utf-8')
    print(f'  {len(fc["features"])} locations → {out_path.name}')
    time.sleep(2)

print('Done.')
