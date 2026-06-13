#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Add HYS (Hämäläisten Ylioppilassäätiö) buildings as a topmost layer.

HYS publishes its properties at https://hys.net/asuminen/kohteet/ (a small set,
~7 buildings in the Käpylä/Koskela area). Each property page gives the street
address. Per-building rents are login-gated (the Domo portal), so they are
maintained out-of-band in offline/data/hys_rents.json (keyed by address) and
merged in here, then shown in the marker popup/tooltip. Geocoded with Nominatim
(shared cache), filtered to the 40-minute commute area, drawn as blue 🏠
markers with their own lower-left toggle (⑤). Cached offline.

Falls back to the cache when offline. Idempotent: replaces the block in place.
"""
import html as html_mod
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

INDEX_URL = 'https://hys.net/asuminen/kohteet/'

root = Path(__file__).resolve().parent
offline = root / 'offline'
index = offline / 'index.html'
data = offline / 'data'
listings_cache = data / 'hys_listings.geojson'
geo_cache_path = data / 'geocode_cache.json'
if not index.exists():
    raise SystemExit('Missing offline/index.html')


def http_get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (offline-map-builder)'})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode('utf-8')


def property_urls():
    h = http_get(INDEX_URL)
    urls = re.findall(r'https://hys\.net/asuminen/kohteet/[a-z0-9-]+/', h)
    return sorted(set(u for u in urls if '/feed/' not in u and not u.endswith('/kohteet/')))


STREET = r'[A-ZÄÖ][a-zäöA-ZÄÖ]+(?:katu|tie|kuja|polku|kaari|tori|ranta|rinne|aukio)\s?\d+[-0-9a-z]*'


def parse_property(page):
    m = re.search(r'<h1[^>]*>(.*?)</h1>', page, re.S)
    name = html_mod.unescape(re.sub(r'<[^>]+>', '', m.group(1)).strip()) if m else 'HYS'
    am = re.search(STREET, page)
    addr = am.group(0) if am else name
    return name, addr


# convex hull + point-in-poly + 40-min hull (same helpers as the HOAS script)
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
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-18) + xi):
            inside = not inside
        j = i
    return inside


geo_cache = {}
if geo_cache_path.exists():
    geo_cache = json.loads(geo_cache_path.read_text(encoding='utf-8'))


def geocode(address):
    street = re.sub(r'(\d+)\s*-\s*\d+', r'\1', address.split(',')[0]).strip()
    q = street + ', Finland'
    if q in geo_cache:
        return geo_cache[q]
    params = urllib.parse.urlencode({
        'q': q, 'format': 'json', 'limit': 1, 'countrycodes': 'fi',
        'viewbox': '24.40,60.45,25.55,60.05', 'bounded': 1,
    })
    ll = None
    try:
        res = json.loads(http_get('https://nominatim.openstreetmap.org/search?' + params))
        if res:
            ll = [round(float(res[0]['lon']), 6), round(float(res[0]['lat']), 6)]
    except Exception as ex:
        print('  geocode failed for %s: %s' % (q, ex))
    time.sleep(1.1)
    geo_cache[q] = ll
    return ll


features = []
try:
    urls = property_urls()
    print('HYS lists %d properties; fetching...' % len(urls))
    hull = load_40min_hull()
    for u in urls:
        try:
            name, addr = parse_property(http_get(u))
        except Exception:
            continue
        time.sleep(0.2)
        ll = geocode(addr)
        if not ll:
            print('  no geocode: %s (%s)' % (name, addr))
            continue
        if hull and not point_in_poly(ll[0], ll[1], hull):
            print('  outside 40-min: %s' % name)
            continue
        features.append({
            'type': 'Feature',
            'properties': {'name': name, 'address': addr, 'url': u},
            'geometry': {'type': 'Point', 'coordinates': ll},
        })
    geo_cache_path.write_text(json.dumps(geo_cache, ensure_ascii=False), encoding='utf-8')
    print('Kept %d HYS buildings inside the 40-min area.' % len(features))
except Exception as e:
    print('Online fetch failed (%s); will reuse cache if present.' % e)

if features:
    fc = {'type': 'FeatureCollection', 'features': features}
    listings_cache.write_text(json.dumps(fc, ensure_ascii=False), encoding='utf-8')
elif listings_cache.exists():
    fc = json.loads(listings_cache.read_text(encoding='utf-8'))
    print('Using existing HYS cache (%d).' % len(fc.get('features', [])))
else:
    fc = {'type': 'FeatureCollection', 'features': []}
    print('No HYS data and no cache; embedding empty layer.')

# Attach real rents (login-gated in Domo) from the out-of-band table, keyed by
# address, so an online re-fetch above never drops them. Re-persist the cache.
rents_path = data / 'hys_rents.json'
if rents_path.exists() and fc.get('features'):
    rents = json.loads(rents_path.read_text(encoding='utf-8'))
    merged = 0
    for f in fc['features']:
        r = rents.get((f.get('properties') or {}).get('address'))
        if r:
            f['properties'].update({
                'min_rent': r['min_rent'], 'max_rent': r['max_rent'],
                'rent_breakdown': r.get('rent_breakdown', ''),
                'rent_source': r.get('source', 'Domo (HYS)'),
            })
            merged += 1
    listings_cache.write_text(json.dumps(fc, ensure_ascii=False), encoding='utf-8')
    print('Merged Domo rents into %d/%d HYS buildings.' % (merged, len(fc['features'])))

# ---- inject ----------------------------------------------------------------
text = index.read_text(encoding='utf-8')
backup = offline / 'index_before_hys_listings.html'
if not backup.exists():
    backup.write_text(text, encoding='utf-8')

script_id = 'hys-listings-final'
for marker in ["<script id='" + script_id + "'>", '<script id="' + script_id + '">']:
    while marker in text:
        before, rest = text.split(marker, 1)
        text = before + (rest.split('</script>', 1)[1] if '</script>' in rest else '')

css = '''
/* HYS home markers (topmost, blue) + active toggle state. */
.hys-home{
  width:26px; height:26px; line-height:26px; text-align:center; font-size:18px;
  background:#fff; border:2px solid #1f6feb; border-radius:50%;
  box-shadow:0 2px 6px rgba(0,0,0,.35);
}
#viewControls .vc-btn.hys-active{ background:#1f6feb; color:#fff; border-color:#1f6feb; }
'''
if 'HYS home markers (topmost, blue)' not in text:
    if '</style>' in text:
        text = text.replace('</style>', css + '</style>', 1)
    elif '</head>' in text:
        text = text.replace('</head>', '<style>' + css + '</style></head>', 1)
    else:
        text = '<style>' + css + '</style>' + chr(10) + text

data_literal = json.dumps(fc, ensure_ascii=False)

js = '''<script id="hys-listings-final">
(function(){
  var HYS = __HYS_GEOJSON__;
  var group = null, on = false;

  function ensureGroup(){
    if(group) return group;
    if(!map.getPane('hysPane')){
      map.createPane('hysPane');
      map.getPane('hysPane').style.zIndex = 651;
    }
    var icon = L.divIcon({className:'hoas-home-wrap',
      html:'<div class="hys-home">🏠</div>', iconSize:[26,26], iconAnchor:[13,13]});
    group = L.layerGroup();
    HYS.features.forEach(function(f){
      var p = f.properties, c = f.geometry.coordinates;
      var html = '<div class="hoas-popup"><b>' + (p.name || p.address) + '</b>'
        + '<br>' + p.address
        + (p.max_rent ? '<br>HYS · <span class="rent">' + p.min_rent + '–' + p.max_rent + ' €/kk</span>'
            + (p.rent_breakdown ? '<br><span class="rent-bd">' + p.rent_breakdown + '</span>' : '')
            : '<br>HYS · <span class="rent">价格见 Domo</span>')
        + '<br><a href="' + p.url + '" target="_blank" rel="noopener">HYS 房源页 →</a></div>';
      L.marker([c[1], c[0]], {icon:icon, pane:'hysPane', riseOnHover:true})
        .bindPopup(html).bindTooltip((p.name || p.address) + (p.max_rent ? ' · ' + p.min_rent + '–' + p.max_rent + ' €' : ''), {direction:'top'})
        .addTo(group);
    });
    return group;
  }

  function toggle(btn){
    if(typeof map === 'undefined') return;
    on = !on;
    if(on){ ensureGroup().addTo(map); } else if(group){ map.removeLayer(group); }
    btn.classList.toggle('hys-active', on);
  }

  function build(){
    var host = document.getElementById('viewControls');
    if(!host) return false;
    if(document.getElementById('hysToggleBtn')) return true;
    var b = document.createElement('button');
    b.id = 'hysToggleBtn';
    b.className = 'vc-btn';
    b.textContent = '⑤ HYS 房源（Domo）';
    b.addEventListener('click', function(){ toggle(b); });
    host.appendChild(b);
    return true;
  }

  function tryBuild(){ try { return build(); } catch(e){ return false; } }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', tryBuild);
  else tryBuild();
  [300, 900, 1800, 3500].forEach(function(ms){ setTimeout(tryBuild, ms); });
})();
</script>'''.replace('__HYS_GEOJSON__', data_literal)

if '</body></html>' in text:
    text = text.replace('</body></html>', js + chr(10) + '</body></html>', 1)
elif '</body>' in text:
    text = text.replace('</body>', js + chr(10) + '</body>', 1)
else:
    text = text + chr(10) + js

index.write_text(text, encoding='utf-8')
print('Done: HYS listings layer injected (%d markers) + toggle ⑤.' % len(fc['features']))
print('Cached at offline/data/hys_listings.geojson; backup index_before_hys_listings.html')
