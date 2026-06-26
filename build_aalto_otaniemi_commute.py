#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build Aalto Otaniemi arrival commute layers from the local HSL GTFS zip.

The output mirrors the existing commute GeoJSON style: each reachable stop is
drawn as a point and, when time remains, a residual walking circle. The scan is
reverse timetable-based: for each sampled morning departure window and time
threshold, it asks whether a stop can still depart late enough to arrive at the
Otaniemi target within the threshold.
"""
import csv
import json
import math
import re
import unicodedata
import urllib.request
import zipfile
from bisect import bisect_right
from collections import defaultdict
from pathlib import Path

from hoas_page_parser import parse_housing_page


HOAS_SITEMAP_URL = 'https://hoas.fi/cost-unit-sitemap.xml'

SERVICE_DATE = '2026-06-09'
SAMPLE_START = '07:30:00'
SAMPLE_END = '08:30:00'
SAMPLE_STEP_MIN = 10
THRESHOLDS = [10, 15, 20, 30, 40]
WALK_SPEED_M_PER_MIN = 80.0
TARGET = {
    'name': 'Aalto University Otaniemi',
    'lat': 60.1842,
    'lon': 24.8269,
}
COLORS = {10: '#22c55e', 15: '#0f766e', 20: '#2563eb', 30: '#f97316', 40: '#7c3aed'}

ROOT = Path(__file__).resolve().parent
OFFLINE = ROOT / 'offline'
DATA = OFFLINE / 'data'
GTFS_ZIP = OFFLINE / 'raw' / 'hsl.zip'
OUT_GEOJSON = DATA / 'commute_aalto_otaniemi_gtfs.geojson'
OUT_META = DATA / 'commute_aalto_otaniemi_gtfs_metadata.json'
OUT_HOAS = DATA / 'hoas_listings_aalto_otaniemi.geojson'
OUT_HYS = DATA / 'hys_listings_aalto_otaniemi.geojson'


def parse_time(s):
    h, m, sec = [int(x) for x in s.split(':')]
    return h * 3600 + m * 60 + sec


def fmt_time(sec):
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f'{h:02d}:{m:02d}:{s:02d}'


def service_date_parts():
    y, m, d = [int(x) for x in SERVICE_DATE.split('-')]
    import datetime as dt
    date = dt.date(y, m, d)
    return date, date.strftime('%Y%m%d'), date.strftime('%A').lower()


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def circle_polygon(lon, lat, radius_m, steps=72):
    if radius_m <= 0:
        return []
    lat_rad = math.radians(lat)
    dlat = radius_m / 111320.0
    dlon = radius_m / (111320.0 * max(math.cos(lat_rad), 1e-6))
    pts = []
    for i in range(steps + 1):
        a = 2 * math.pi * i / steps
        pts.append([round(lon + dlon * math.cos(a), 12), round(lat + dlat * math.sin(a), 12)])
    return pts


def convex_hull(points):
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (a[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    # Correct orientation test for lon/lat points.
    def orient(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and orient(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and orient(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def zip_rows(zf, name):
    with zf.open(name) as fh:
        text = (line.decode('utf-8-sig') for line in fh)
        yield from csv.DictReader(text)


def active_services(zf):
    _, ymd, weekday = service_date_parts()
    active = set()
    for row in zip_rows(zf, 'calendar.txt'):
        if row.get('start_date', '') <= ymd <= row.get('end_date', '') and row.get(weekday) == '1':
            active.add(row['service_id'])
    for row in zip_rows(zf, 'calendar_dates.txt'):
        if row.get('date') != ymd:
            continue
        if row.get('exception_type') == '1':
            active.add(row['service_id'])
        elif row.get('exception_type') == '2':
            active.discard(row['service_id'])
    return active


def read_gtfs():
    if not GTFS_ZIP.exists():
        raise SystemExit(f'Missing {GTFS_ZIP}')
    start = parse_time(SAMPLE_START)
    end = parse_time(SAMPLE_END)
    max_deadline = end + max(THRESHOLDS) * 60
    min_time = start - 5 * 60

    with zipfile.ZipFile(GTFS_ZIP) as zf:
        services = active_services(zf)
        print(f'Active services on {SERVICE_DATE}: {len(services)}')

        stops = {}
        for row in zip_rows(zf, 'stops.txt'):
            sid = row.get('stop_id')
            if not sid:
                continue
            stops[sid] = {
                'name': row.get('stop_name') or sid,
                'lat': float(row['stop_lat']),
                'lon': float(row['stop_lon']),
            }
        print(f'Stops: {len(stops)}')

        active_trips = set()
        for row in zip_rows(zf, 'trips.txt'):
            if row.get('service_id') in services:
                active_trips.add(row['trip_id'])
        print(f'Active trips: {len(active_trips)}')

        connections = []
        prev_by_trip = {}
        total_rows = 0
        for row in zip_rows(zf, 'stop_times.txt'):
            total_rows += 1
            trip_id = row.get('trip_id')
            if trip_id not in active_trips:
                continue
            sid = row.get('stop_id')
            if sid not in stops:
                continue
            arr = parse_time(row['arrival_time'])
            dep = parse_time(row['departure_time'])
            prev = prev_by_trip.get(trip_id)
            if prev:
                p_sid, p_dep = prev
                if p_dep <= max_deadline and arr >= min_time and p_sid != sid:
                    connections.append((p_dep, arr, p_sid, sid))
            prev_by_trip[trip_id] = (sid, dep)
        connections.sort(key=lambda x: x[0], reverse=True)
        print(f'Stop time rows scanned: {total_rows}')
        print(f'Connections in window: {len(connections)}')
    return stops, connections


def sample_departures():
    start = parse_time(SAMPLE_START)
    end = parse_time(SAMPLE_END)
    step = SAMPLE_STEP_MIN * 60
    out = []
    t = start
    while t <= end:
        out.append(t)
        t += step
    return out


def reverse_reachable(stops, connections):
    samples = sample_departures()
    target_walk = {}
    for sid, s in stops.items():
        dist = haversine_m(s['lat'], s['lon'], TARGET['lat'], TARGET['lon'])
        if dist <= max(THRESHOLDS) * WALK_SPEED_M_PER_MIN:
            target_walk[sid] = dist / WALK_SPEED_M_PER_MIN * 60.0

    best_by_threshold = {m: {} for m in THRESHOLDS}
    summaries = []
    for sample in samples:
        summary = {'departure': fmt_time(sample)}
        for minutes in THRESHOLDS:
            deadline = sample + minutes * 60
            latest = {}
            for sid, walk_sec in target_walk.items():
                if walk_sec <= minutes * 60:
                    latest[sid] = deadline - walk_sec
            for dep, arr, a, b in connections:
                if dep < sample:
                    break
                if arr <= deadline and latest.get(b, -1) >= arr and dep > latest.get(a, -1):
                    latest[a] = dep
            count = 0
            for sid, latest_dep in latest.items():
                if latest_dep < sample:
                    continue
                duration_min = round((deadline - latest_dep) / 60.0, 1)
                old = best_by_threshold[minutes].get(sid)
                if old is None or duration_min < old:
                    best_by_threshold[minutes][sid] = duration_min
                count += 1
            summary[f'reachable{minutes}'] = count
        summaries.append(summary)
        print('Sample', fmt_time(sample), ' '.join(f'{m}m={summary[f"reachable{m}"]}' for m in THRESHOLDS))
    return best_by_threshold, summaries


def make_features(stops, best_by_threshold):
    features = []
    for minutes in THRESHOLDS:
        outline_pts = []
        for sid, arrival_min in sorted(best_by_threshold[minutes].items()):
            s = stops[sid]
            residual = max(0.0, (minutes - arrival_min) * WALK_SPEED_M_PER_MIN)
            if residual >= 25:
                coords = circle_polygon(s['lon'], s['lat'], residual)
                if coords:
                    features.append({
                        'type': 'Feature',
                        'properties': {
                            'kind': 'residual_walk_circle',
                            'target': 'aalto_otaniemi',
                            'minutes': minutes,
                            'stop_id': sid,
                            'stop_name': s['name'],
                            'arrival_min': arrival_min,
                            'residual_walk_m': int(round(residual)),
                            'color': COLORS[minutes],
                        },
                        'geometry': {'type': 'Polygon', 'coordinates': [coords]},
                    })
                    outline_pts.extend((x, y) for x, y in coords[::6])
            else:
                outline_pts.append((s['lon'], s['lat']))
            features.append({
                'type': 'Feature',
                'properties': {
                    'kind': 'reachable_stop',
                    'target': 'aalto_otaniemi',
                    'minutes': minutes,
                    'stop_id': sid,
                    'stop_name': s['name'],
                    'arrival_min': arrival_min,
                    'color': COLORS[minutes],
                },
                'geometry': {'type': 'Point', 'coordinates': [round(s['lon'], 6), round(s['lat'], 6)]},
            })
        hull = convex_hull(outline_pts)
        if len(hull) >= 3:
            hull.append(hull[0])
            features.append({
                'type': 'Feature',
                'properties': {
                    'kind': 'convex_hull_outline',
                    'target': 'aalto_otaniemi',
                    'minutes': minutes,
                    'color': COLORS[minutes],
                },
                'geometry': {'type': 'Polygon', 'coordinates': [[list(p) for p in hull]]},
            })
    return features


def _addr_slug(address):
    """Convert an address to a HOAS URL slug (lowercase, Finnish chars stripped)."""
    nfkd = unicodedata.normalize('NFKD', address.lower())
    ascii_s = ''.join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', '-', ascii_s).strip('-')


def _gather_hoas_buildings():
    """Return HOAS GeoJSON features covering the full Helsinki metro area.

    Extends hoas_listings.geojson (filtered to Pasteurinkatu commute hull) with
    buildings from the geocode cache that were excluded by that hull filter but
    are relevant for the Aalto Otaniemi commute area (e.g. Matinkylä, Olari).
    Confirms HOAS membership against the live sitemap when online; falls back
    to slug matching when offline.
    """
    base_path = DATA / 'hoas_listings.geojson'
    geo_cache_path = DATA / 'geocode_cache.json'

    features = []
    base_addrs = set()
    if base_path.exists():
        features = json.loads(base_path.read_text(encoding='utf-8')).get('features', [])
        base_addrs = {f['properties']['address'] for f in features}

    if not geo_cache_path.exists():
        return features
    geo_cache = json.loads(geo_cache_path.read_text(encoding='utf-8'))

    # Load HYS addresses so we don't accidentally include them.
    hys_addrs = set()
    for hys_src in [DATA / 'hys_listings.geojson']:
        if hys_src.exists():
            for f in json.loads(hys_src.read_text(encoding='utf-8')).get('features', []):
                p = f.get('properties', {})
                hys_addrs.add((p.get('name') or p.get('address') or '').split(',')[0].strip())

    # Fetch HOAS sitemap to confirm building membership (best-effort; offline OK).
    hoas_slugs = set()
    try:
        req = urllib.request.Request(HOAS_SITEMAP_URL, headers={'User-Agent': 'Mozilla/5.0 (offline-map)'})
        with urllib.request.urlopen(req, timeout=12) as r:
            xml = r.read().decode('utf-8')
        hoas_slugs = set(re.findall(r'/housing/([a-z0-9-]+)/', xml))
        print(f'HOAS sitemap: {len(hoas_slugs)} building slugs fetched')
    except Exception as e:
        print(f'HOAS sitemap unavailable ({e}); slug-matching from cache')

    seen_coords = {
        (f['geometry']['coordinates'][0], f['geometry']['coordinates'][1])
        for f in features
    }

    city_suffixes = (
        ', Espoo, Finland', ', Helsinki, Finland', ', Vantaa, Finland',
        ', Kauniainen, Finland', ', Finland',
    )
    added = 0
    for cache_key, coords in geo_cache.items():
        if not coords:
            continue
        addr = cache_key
        for suf in city_suffixes:
            if addr.endswith(suf):
                addr = addr[:-len(suf)]
                break
        addr = addr.strip()
        if addr in base_addrs:
            continue
        if any(addr.startswith(h) for h in hys_addrs if h):
            continue
        lon, lat = float(coords[0]), float(coords[1])
        if (lon, lat) in seen_coords:
            continue
        slug = _addr_slug(addr)
        if hoas_slugs:
            # Accept both exact match and prefix match: geocache stores only the
            # first component of multi-address slugs like "kirstinharju-1-kirstinharju-3".
            if slug in hoas_slugs:
                real_slug = slug
            else:
                real_slug = next((s for s in hoas_slugs if s.startswith(slug + '-')), None)
                if real_slug is None:
                    continue
            slug = real_slug
        else:
            # Offline fallback: only include entries whose slug looks like a street
            # address (has at least one digit = house number).
            if not re.search(r'\d', slug):
                continue
        url = f'https://hoas.fi/en/housing/{slug}/'
        min_rent, max_rent, condition = _fetch_hoas_details(url)
        features.append({
            'type': 'Feature',
            'properties': {
                'address': addr, 'min_rent': min_rent, 'max_rent': max_rent,
                'condition': condition, 'url': url,
            },
            'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
        })
        seen_coords.add((lon, lat))
        base_addrs.add(addr)
        added += 1

    if added:
        print(f'_gather_hoas_buildings: added {added} extra buildings from geocache')
    return features


def _fetch_hoas_details(url):
    """Fetch structured HOAS rent and condition fields, or empty values on failure."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (offline-map)'})
        with urllib.request.urlopen(req, timeout=10) as r:
            page = r.read().decode('utf-8', errors='replace')
        details = parse_housing_page(page)
        return details['min_rent'], details['max_rent'], details['condition']
    except Exception:
        pass
    return None, None, None


def annotate_listings(stops, best40):
    stop_items = sorted(
        ((s['lat'], s['lon'], sid, best40[sid]) for sid, s in stops.items() if sid in best40),
        key=lambda x: x[0],
    )
    lats = [x[0] for x in stop_items]

    def best_time(lat, lon):
        if not stop_items:
            return None
        # 40 min × 80 m/min ≈ 0.029° lat. Use a generous window before haversine.
        lo = max(0, bisect_right(lats, lat - 0.04) - 1)
        hi = min(len(stop_items), bisect_right(lats, lat + 0.04) + 1)
        best = None
        for slat, slon, sid, stop_min in stop_items[lo:hi]:
            walk_min = haversine_m(lat, lon, slat, slon) / WALK_SPEED_M_PER_MIN
            # stop_min = transit+walk time from the stop to Aalto (not incl. waiting).
            # walk_min = walk from listing to the stop.
            # Feasibility: walk_min <= (latest_dep - sample) / 60 (guaranteed when
            # total <= 40 because total = walk_min + stop_min and deadline = sample+40).
            total = stop_min + walk_min
            if total <= 40 and (best is None or total < best):
                best = total
        return round(best, 1) if best is not None else None

    # ---- HOAS: use the expanded building list (all metro-area buildings) -----
    hoas_features = _gather_hoas_buildings()
    hoas_reachable = 0
    for f in hoas_features:
        c = f.get('geometry', {}).get('coordinates') or []
        if len(c) < 2:
            continue
        t = best_time(c[1], c[0])
        p = f.setdefault('properties', {})
        p['aalto_otaniemi_min'] = t
        p['aalto_otaniemi_40min'] = t is not None and t <= 40
        if p['aalto_otaniemi_40min']:
            hoas_reachable += 1
    hoas_fc = {'type': 'FeatureCollection', 'features': hoas_features}
    OUT_HOAS.write_text(json.dumps(hoas_fc, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'{OUT_HOAS.name}: {hoas_reachable}/{len(hoas_features)} listings <=40 min')

    # ---- HYS: read hys_listings.geojson as-is (small, no expansion needed) --
    hys_src = DATA / 'hys_listings.geojson'
    if hys_src.exists():
        hys_gj = json.loads(hys_src.read_text(encoding='utf-8'))
        hys_reachable = 0
        for f in hys_gj.get('features', []):
            c = f.get('geometry', {}).get('coordinates') or []
            if len(c) < 2:
                continue
            t = best_time(c[1], c[0])
            p = f.setdefault('properties', {})
            p['aalto_otaniemi_min'] = t
            p['aalto_otaniemi_40min'] = t is not None and t <= 40
            if p['aalto_otaniemi_40min']:
                hys_reachable += 1
        OUT_HYS.write_text(json.dumps(hys_gj, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        print(f'{OUT_HYS.name}: {hys_reachable}/{len(hys_gj.get("features", []))} listings <=40 min')


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    stops, connections = read_gtfs()
    best_by_threshold, summaries = reverse_reachable(stops, connections)
    features = make_features(stops, best_by_threshold)
    fc = {'type': 'FeatureCollection', 'features': features}
    OUT_GEOJSON.write_text(json.dumps(fc, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    annotate_listings(stops, best_by_threshold[40])
    meta = {
        'target': TARGET,
        'service_date': SERVICE_DATE,
        'sample_start': SAMPLE_START,
        'sample_end': SAMPLE_END,
        'sample_step_min': SAMPLE_STEP_MIN,
        'thresholds_min': THRESHOLDS,
        'walk_speed_m_per_min': WALK_SPEED_M_PER_MIN,
        'reachable_stops': {str(m): len(best_by_threshold[m]) for m in THRESHOLDS},
        'sample_summaries': summaries,
        'feature_count': len(features),
        'method': 'Reverse GTFS timetable scan for arrivals at Aalto Otaniemi; residual walking circles at origin side',
    }
    OUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Wrote {OUT_GEOJSON}')
    print(f'Wrote {OUT_META}')


if __name__ == '__main__':
    main()
