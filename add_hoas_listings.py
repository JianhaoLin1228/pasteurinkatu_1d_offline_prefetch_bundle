#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Add ALL HOAS buildings (with rent) as topmost home-icon markers.

Pipeline (online fetch -> offline cache):
  1. Read the HOAS cost-unit sitemap to list every building page (~126), then
     fetch each page and extract its address (h1) and rent figures.
  2. Geocode each address with OpenStreetMap Nominatim, bounded to the Helsinki
     metro viewbox (accurate, no city ambiguity). Cached on disk across runs.
  3. Keep only buildings inside the 40-minute commute area
     (convex hull of the 40-min isochrone in offline/data).
  4. Cache the result at offline/data/hoas_listings.geojson and embed it inline.
  5. Render a topmost layer of 🏠 markers; clicking one shows the rent (price).
     A lower-left toggle button switches the layer on/off.

Re-run to refresh prices. Falls back to the cache when offline.
Idempotent: re-running replaces the injected block in place.
"""
import html as html_mod
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from hoas_page_parser import parse_housing_page

SITEMAP_URL = 'https://hoas.fi/cost-unit-sitemap.xml'

root = Path(__file__).resolve().parent
offline = root / 'offline'
index = offline / 'index.html'
data = offline / 'data'
listings_cache = data / 'hoas_listings.geojson'
geo_cache_path = data / 'geocode_cache.json'

if not index.exists():
    raise SystemExit('Missing offline/index.html')


def http_get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (offline-map-builder)'})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode('utf-8')


def building_urls():
    xml = http_get(SITEMAP_URL)
    urls = re.findall(r'<loc>(https://hoas\.fi/en/housing/[a-z0-9-]+/)</loc>', xml)
    # drop the archive index page if present
    return sorted(set(u for u in urls if not u.endswith('/housing/')))


def parse_building(page):
    details = parse_housing_page(page)
    return (details['address'], details['min_rent'], details['max_rent'], details['condition'])


def convex_hull(points):
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def collect_coords(obj, out):
    if isinstance(obj, list):
        if obj and isinstance(obj[0], (int, float)) and len(obj) >= 2:
            out.append((obj[0], obj[1]))
        else:
            for x in obj:
                collect_coords(x, out)


def load_40min_hull():
    for name in ['commute_40min.geojson', 'commute_10_15_40_gtfs.geojson']:
        p = data / name
        if not p.exists():
            continue
        gj = json.loads(p.read_text(encoding='utf-8'))
        pts = []
        for f in gj.get('features', []):
            if int((f.get('properties') or {}).get('minutes', 0)) == 40:
                collect_coords(f['geometry']['coordinates'], pts)
        if len(pts) >= 3:
            return convex_hull(pts)
    return None


def point_in_poly(x, y, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-18) + xi):
            inside = not inside
        j = i
    return inside


# ---- 2. geocode (cached) ----------------------------------------------------
geo_cache = {}
if geo_cache_path.exists():
    geo_cache = json.loads(geo_cache_path.read_text(encoding='utf-8'))


def geocode(address):
    # First street of a multi-address building, bounded to the Helsinki metro
    # so the right city is chosen without needing a city field.
    street = address.split('/')[0].split(',')[0].strip()
    q = street + ', Finland'
    if q in geo_cache:
        return geo_cache[q]
    params = urllib.parse.urlencode({
        'q': q, 'format': 'json', 'limit': 1, 'countrycodes': 'fi',
        'viewbox': '24.40,60.45,25.55,60.05', 'bounded': 1,
    })
    url = 'https://nominatim.openstreetmap.org/search?' + params
    ll = None
    try:
        res = json.loads(http_get(url))
        if res:
            ll = [round(float(res[0]['lon']), 6), round(float(res[0]['lat']), 6)]
    except Exception as ex:
        print('  geocode failed for %s: %s' % (q, ex))
    time.sleep(1.1)  # Nominatim usage policy
    geo_cache[q] = ll
    return ll


# ---- 1. crawl every building page -------------------------------------------
features = []
try:
    urls = building_urls()
    print('Sitemap lists %d HOAS buildings; crawling...' % len(urls))
    hull = load_40min_hull()
    kept = skipped = failed = 0
    for n, u in enumerate(urls, 1):
        try:
            address, min_rent, max_rent, condition = parse_building(http_get(u))
        except Exception as ex:
            failed += 1
            continue
        time.sleep(0.2)  # be polite to hoas.fi
        if not address:
            failed += 1
            continue
        ll = geocode(address)
        if not ll:
            failed += 1
            continue
        if hull and not point_in_poly(ll[0], ll[1], hull):
            skipped += 1
            continue  # outside the 40-min commute area
        features.append({
            'type': 'Feature',
            'properties': {
                'address': address,
                'min_rent': min_rent,
                'max_rent': max_rent,
                'condition': condition,
                'url': u,
            },
            'geometry': {'type': 'Point', 'coordinates': ll},
        })
        kept += 1
        if n % 20 == 0:
            print('  ...%d/%d (kept %d, outside %d, failed %d)' % (n, len(urls), kept, skipped, failed))
        geo_cache_path.write_text(json.dumps(geo_cache, ensure_ascii=False), encoding='utf-8')
    print('Crawl done: kept %d inside 40-min, %d outside, %d failed.' % (kept, skipped, failed))
except Exception as e:
    print('Online crawl failed (%s); will reuse cache if present.' % e)

if features:
    fc = {'type': 'FeatureCollection', 'features': features}
    listings_cache.write_text(json.dumps(fc, ensure_ascii=False), encoding='utf-8')
    print('Kept %d HOAS listings inside the 40-min area; cached offline.' % len(features))
elif listings_cache.exists():
    fc = json.loads(listings_cache.read_text(encoding='utf-8'))
    print('Using existing offline cache (%d listings).' % len(fc.get('features', [])))
else:
    fc = {'type': 'FeatureCollection', 'features': []}
    print('No listings available and no cache; embedding empty layer.')

# ---- 5. inject the layer ----------------------------------------------------
text = index.read_text(encoding='utf-8')
backup = offline / 'index_before_hoas_listings.html'
if not backup.exists():
    backup.write_text(text, encoding='utf-8')

script_id = 'hoas-listings-final'
for marker in ["<script id='" + script_id + "'>", '<script id="' + script_id + '">']:
    while marker in text:
        before, rest = text.split(marker, 1)
        text = before + (rest.split('</script>', 1)[1] if '</script>' in rest else '')

css = '''
/* HOAS home markers (topmost) + active toggle state. */
.hoas-home-wrap{ background:none; border:none; }
.hoas-home{
  width:26px; height:26px; line-height:26px; text-align:center; font-size:18px;
  background:#fff; border:2px solid #d62728; border-radius:50%;
  box-shadow:0 2px 6px rgba(0,0,0,.35);
}
.hoas-popup b{ font-size:13px; }
.hoas-popup .rent{ color:#d62728; font-weight:700; }
#viewControls .vc-btn.hoas-active{ background:#d62728; color:#fff; border-color:#d62728; }
'''
if 'HOAS home markers (topmost)' not in text:
    if '</style>' in text:
        text = text.replace('</style>', css + '</style>', 1)
    elif '</head>' in text:
        text = text.replace('</head>', '<style>' + css + '</style></head>', 1)
    else:
        text = '<style>' + css + '</style>' + chr(10) + text

data_literal = json.dumps(fc, ensure_ascii=False)

js = '''<script id="hoas-listings-final">
(function(){
  var HOAS = __HOAS_GEOJSON__;
  var group = null, on = false;

  function priceLine(p){
    if(p.min_rent == null) return '价格请见链接';
    var r = (p.min_rent === p.max_rent) ? (p.min_rent + ' €/kk')
              : (p.min_rent + '–' + p.max_rent + ' €/kk');
    return r;
  }

  function ensureGroup(){
    if(group) return group;
    if(!map.getPane('hoasPane')){
      map.createPane('hoasPane');
      map.getPane('hoasPane').style.zIndex = 650;  // above routes/markers
    }
    var icon = L.divIcon({className:'hoas-home-wrap',
      html:'<div class="hoas-home">🏠</div>', iconSize:[26,26], iconAnchor:[13,13]});
    group = L.layerGroup();
    HOAS.features.forEach(function(f){
      var p = f.properties, c = f.geometry.coordinates;
      var m2 = (p.min_m2 != null) ? ('<br>面积 ' + p.min_m2 + '–' + p.max_m2 + ' m²') : '';
      var avail = (p.available != null) ? ('<br>可租 ' + p.available + ' 套') : '';
      var html = '<div class="hoas-popup"><b>' + (p.address || 'HOAS') + '</b>'
        + (p.area ? ('<br>' + p.area) : '')
        + '<br><span class="rent">' + priceLine(p) + '</span>' + m2 + avail
        + '<br><a href="' + p.url + '" target="_blank" rel="noopener">HOAS 房源页 →</a></div>';
      L.marker([c[1], c[0]], {icon:icon, pane:'hoasPane', riseOnHover:true})
        .bindPopup(html).bindTooltip(priceLine(p), {direction:'top'})
        .addTo(group);
    });
    return group;
  }

  function toggle(btn){
    if(typeof map === 'undefined') return;
    on = !on;
    if(on){ ensureGroup().addTo(map); } else if(group){ map.removeLayer(group); }
    btn.classList.toggle('hoas-active', on);
  }

  function build(){
    var host = document.getElementById('viewControls');
    if(!host) return false;
    if(document.getElementById('hoasToggleBtn')) return true;
    var b = document.createElement('button');
    b.id = 'hoasToggleBtn';
    b.className = 'vc-btn';
    b.textContent = '④ HOAS 房源（价格）';
    b.addEventListener('click', function(){ toggle(b); });
    host.appendChild(b);
    return true;
  }

  function tryBuild(){ try { return build(); } catch(e){ return false; } }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', tryBuild);
  else tryBuild();
  [300, 900, 1800, 3500].forEach(function(ms){ setTimeout(tryBuild, ms); });
})();
</script>'''.replace('__HOAS_GEOJSON__', data_literal)

if '</body></html>' in text:
    text = text.replace('</body></html>', js + chr(10) + '</body></html>', 1)
elif '</body>' in text:
    text = text.replace('</body>', js + chr(10) + '</body>', 1)
else:
    text = text + chr(10) + js

index.write_text(text, encoding='utf-8')
print('Done: HOAS listings layer injected (%d markers) + toggle button.' % len(fc['features']))
print('Cached at offline/data/hoas_listings.geojson; backup index_before_hoas_listings.html')
