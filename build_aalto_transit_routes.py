#!/usr/bin/env python3
"""Build route geometry for services that make the Aalto 40-minute area reachable.

The selection exactly follows the reverse GTFS scan used by
``build_aalto_otaniemi_commute.py``: a route is retained only when one of its
scheduled connections improves a stop's latest feasible departure time during
the 07:30--08:30 samples.  It therefore includes buses, metro, rail, trams,
and ferries whenever they contribute to the displayed 40-minute commute area.

The output replaces the map's embedded route GeoJSON and records the selected
lines in ``offline/data/aalto_40min_routes_metadata.json``.
"""
import csv
import json
import math
import re
import zipfile
from collections import defaultdict
from pathlib import Path

import build_aalto_otaniemi_commute as commute


ROOT = Path(__file__).resolve().parent
GTFS_ZIP = ROOT / 'offline' / 'raw' / 'hsl.zip'
DATA = ROOT / 'offline' / 'data'
INDEX = ROOT / 'offline' / 'index.html'
ROUTES_OUT = DATA / 'routes.geojson'
META_OUT = DATA / 'aalto_40min_routes_metadata.json'

WINDOW_MINUTES = 40
PALETTE = ('#2563eb', '#dc2626', '#059669', '#7c3aed', '#ea580c', '#0891b2',
           '#be123c', '#4f46e5', '#65a30d', '#c2410c', '#0f766e', '#9333ea')


def rows(zf, name):
    with zf.open(name) as fh:
        yield from csv.DictReader(line.decode('utf-8-sig') for line in fh)


def parse_time(value):
    hour, minute, second = (int(part) for part in value.split(':'))
    return hour * 3600 + minute * 60 + second


def haversine_m(lat1, lon1, lat2, lon2):
    radius = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def active_services(zf):
    _, ymd, weekday = commute.service_date_parts()
    active = set()
    for row in rows(zf, 'calendar.txt'):
        if row.get('start_date', '') <= ymd <= row.get('end_date', '') and row.get(weekday) == '1':
            active.add(row['service_id'])
    for row in rows(zf, 'calendar_dates.txt'):
        if row.get('date') == ymd:
            if row.get('exception_type') == '1':
                active.add(row['service_id'])
            elif row.get('exception_type') == '2':
                active.discard(row['service_id'])
    return active


def color_for(route):
    value = (route.get('route_color') or '').strip()
    if re.fullmatch(r'[0-9A-Fa-f]{6}', value):
        return '#' + value
    return PALETTE[sum(ord(char) for char in route['route_id']) % len(PALETTE)]


def read_gtfs():
    if not GTFS_ZIP.exists():
        raise SystemExit(f'Missing GTFS archive: {GTFS_ZIP}')
    start = parse_time(commute.SAMPLE_START)
    end = parse_time(commute.SAMPLE_END)
    max_deadline = end + WINDOW_MINUTES * 60
    min_time = start - 5 * 60

    with zipfile.ZipFile(GTFS_ZIP) as zf:
        services = active_services(zf)
        stops = {
            row['stop_id']: (float(row['stop_lat']), float(row['stop_lon']))
            for row in rows(zf, 'stops.txt') if row.get('stop_id')
        }
        route_by_id = {row['route_id']: row for row in rows(zf, 'routes.txt') if row.get('route_id')}
        trips = {}
        for row in rows(zf, 'trips.txt'):
            if row.get('service_id') in services and row.get('route_id') in route_by_id:
                trips[row['trip_id']] = (row['route_id'], row.get('shape_id') or '')

        connections, previous = [], {}
        for row in rows(zf, 'stop_times.txt'):
            trip_id = row.get('trip_id')
            if trip_id not in trips or row.get('stop_id') not in stops:
                continue
            arrival, departure = parse_time(row['arrival_time']), parse_time(row['departure_time'])
            prior = previous.get(trip_id)
            if prior:
                from_stop, from_departure = prior
                if from_departure <= max_deadline and arrival >= min_time and from_stop != row['stop_id']:
                    connections.append((from_departure, arrival, from_stop, row['stop_id'], trip_id))
            previous[trip_id] = (row['stop_id'], departure)

        selected_routes = set()
        target_walk = {
            stop_id: haversine_m(lat, lon, commute.TARGET['lat'], commute.TARGET['lon'])
            / commute.WALK_SPEED_M_PER_MIN * 60
            for stop_id, (lat, lon) in stops.items()
        }
        target_walk = {stop_id: seconds for stop_id, seconds in target_walk.items()
                       if seconds <= WINDOW_MINUTES * 60}
        connections.sort(key=lambda item: item[0], reverse=True)

        sample = start
        while sample <= end:
            deadline = sample + WINDOW_MINUTES * 60
            latest = {stop_id: deadline - walk for stop_id, walk in target_walk.items()}
            for departure, arrival, from_stop, to_stop, trip_id in connections:
                if departure < sample:
                    break
                if arrival <= deadline and latest.get(to_stop, -1) >= arrival and departure > latest.get(from_stop, -1):
                    latest[from_stop] = departure
                    selected_routes.add(trips[trip_id][0])
            sample += commute.SAMPLE_STEP_MIN * 60

        selected_shapes = {
            (route_id, shape_id) for route_id, shape_id in trips.values()
            if route_id in selected_routes and shape_id
        }
        points = defaultdict(list)
        wanted_shape_ids = {shape_id for _, shape_id in selected_shapes}
        for row in rows(zf, 'shapes.txt'):
            shape_id = row.get('shape_id')
            if shape_id in wanted_shape_ids:
                points[shape_id].append((int(row['shape_pt_sequence']),
                                         round(float(row['shape_pt_lon']), 6),
                                         round(float(row['shape_pt_lat']), 6)))

    return route_by_id, selected_routes, selected_shapes, points


def build_features(route_by_id, selected_routes, selected_shapes, points):
    features = []
    for route_id, shape_id in sorted(selected_shapes, key=lambda item: (route_by_id[item[0]].get('route_short_name', ''), item[1])):
        coordinates = [[lon, lat] for _, lon, lat in sorted(points[shape_id])]
        if len(coordinates) < 2:
            continue
        route = route_by_id[route_id]
        features.append({
            'type': 'Feature',
            'properties': {
                'shape_id': shape_id,
                'route_id': route_id,
                'route_short_name': route.get('route_short_name') or route_id,
                'route_long_name': route.get('route_long_name') or '',
                'route_type': route.get('route_type') or '',
                'color': color_for(route),
                'point_count': len(coordinates),
            },
            'geometry': {'type': 'LineString', 'coordinates': coordinates},
        })
    if not features:
        raise SystemExit('No route shapes selected; check the GTFS date and service calendar.')
    return features


def replace_embedded_data(routes, metadata):
    text = INDEX.read_text(encoding='utf-8')
    compact_routes = json.dumps(routes, ensure_ascii=False, separators=(',', ':'))
    compact_meta = json.dumps(metadata, ensure_ascii=False, separators=(',', ':'))
    text, route_count = re.subn(
        r'const ROUTES_GEOJSON = .*?;\nconst STOPS_DATA =',
        'const ROUTES_GEOJSON = ' + compact_routes + ';\nconst STOPS_DATA =',
        text, count=1, flags=re.S)
    text, meta_count = re.subn(
        r'const META_DATA = .*?;\nconst CENTER=',
        'const META_DATA = ' + compact_meta + ';\nconst CENTER=',
        text, count=1, flags=re.S)
    if route_count != 1 or meta_count != 1:
        raise SystemExit('Could not locate the embedded route data in offline/index.html')
    INDEX.write_text(text, encoding='utf-8')


def main():
    route_by_id, selected_routes, selected_shapes, points = read_gtfs()
    features = build_features(route_by_id, selected_routes, selected_shapes, points)
    route_names = sorted({feature['properties']['route_short_name'] for feature in features}, key=str.casefold)
    metadata = {
        'service_date': commute.SERVICE_DATE,
        'sample_window': f'{commute.SAMPLE_START}-{commute.SAMPLE_END}',
        'threshold_minutes': WINDOW_MINUTES,
        'selection_method': 'Routes whose scheduled GTFS connections improve the Aalto reverse-reachable 40-minute scan',
        'routes': route_names,
        'route_count': len(selected_routes),
        'feature_count': len(features),
        'shape_point_count': sum(feature['properties']['point_count'] for feature in features),
    }
    collection = {'type': 'FeatureCollection', 'features': features}
    ROUTES_OUT.write_text(json.dumps(collection, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    META_OUT.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    replace_embedded_data(collection, metadata)
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
