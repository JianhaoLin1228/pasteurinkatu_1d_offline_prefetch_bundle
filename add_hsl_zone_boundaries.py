#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Add accurate dashed HSL fare-zone boundaries (A/B/C/D) with a toggle button.

Uses the OFFICIAL HSL fare-zone geometry (open data: "HSL:n maksuvyöhykkeet",
ArcGIS Hub dataset 89b6b5142a9b4bb9a5c5f4404ff28963_0). It is fetched online,
cleaned (zone label + rounded coords) and cached offline at
offline/data/hsl_zones.geojson, then embedded inline and drawn as dashed,
fill-less (color-less) zone outlines, off by default, toggled by a button in
the lower-left control stack. Falls back to the cached file when offline.

Idempotent: re-running replaces the injected block in place.
"""
import json
import urllib.request
from pathlib import Path

DATASET = '89b6b5142a9b4bb9a5c5f4404ff28963_0'
SOURCE_URL = 'https://opendata.arcgis.com/datasets/%s.geojson' % DATASET

root = Path(__file__).resolve().parent
offline = root / 'offline'
index = offline / 'index.html'
cache = offline / 'data' / 'hsl_zones.geojson'
if not index.exists():
    raise SystemExit('Missing offline/index.html')


def round_coords(obj, nd=5):
    if isinstance(obj, list):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(obj[0]), nd), round(float(obj[1]), nd)]
        return [round_coords(x, nd) for x in obj]
    return obj


def clean(raw):
    feats = []
    for f in raw.get('features', []):
        zone = f.get('properties', {}).get('Zone') or f.get('properties', {}).get('Nimi')
        if not zone:
            continue
        feats.append({
            'type': 'Feature',
            'properties': {'zone': zone, 'source': 'HSL maksuvyöhykkeet (open data)'},
            'geometry': {'type': f['geometry']['type'],
                         'coordinates': round_coords(f['geometry']['coordinates'])},
        })
    feats.sort(key=lambda f: f['properties']['zone'])
    return {'type': 'FeatureCollection', 'features': feats}


# Fetch official zones (online); fall back to the existing offline cache.
zones = None
try:
    req = urllib.request.Request(SOURCE_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = json.loads(resp.read().decode('utf-8'))
    zones = clean(raw)
    print('Fetched official HSL zones online (%d features).' % len(zones['features']))
except Exception as e:
    if cache.exists():
        cached = json.loads(cache.read_text(encoding='utf-8'))
        # Reuse only if it is the official-shaped cache (has polygon geometry).
        if cached.get('features') and cached['features'][0]['geometry']['type'] in ('Polygon', 'MultiPolygon'):
            zones = cached
            print('Offline: reusing cached offline/data/hsl_zones.geojson.')
    if zones is None:
        raise SystemExit('Could not fetch HSL zones and no usable cache: %s' % e)

cache.write_text(json.dumps(zones, ensure_ascii=False), encoding='utf-8')

text = index.read_text(encoding='utf-8')
backup = offline / 'index_before_hsl_zone_boundaries.html'
if not backup.exists():
    backup.write_text(text, encoding='utf-8')

script_id = 'hsl-zone-boundaries-final'
for marker in ["<script id='" + script_id + "'>", '<script id="' + script_id + '">']:
    while marker in text:
        before, rest = text.split(marker, 1)
        text = before + (rest.split('</script>', 1)[1] if '</script>' in rest else '')

css = '''
/* Active state for the HSL zone toggle button. */
#viewControls .vc-btn.active{
  background:#0969da; color:#fff; border-color:#0969da;
}
.hsl-zone-label{ background:rgba(255,255,255,.85); border:1px solid #999; border-radius:6px;
  padding:0 5px; font-weight:700; color:#333; font-size:12px; }
'''
if 'Active state for the HSL zone toggle button.' not in text:
    if '</style>' in text:
        text = text.replace('</style>', css + '</style>', 1)
    elif '</head>' in text:
        text = text.replace('</head>', '<style>' + css + '</style></head>', 1)
    else:
        text = '<style>' + css + '</style>' + chr(10) + text

data_literal = json.dumps(zones, ensure_ascii=False)

js = '''<script id="hsl-zone-boundaries-final">
(function(){
  // Official HSL fare zones (open data), cached offline.
  var ZONES = __ZONES_GEOJSON__;
  var group = null, on = false;

  function ensureGroup(){
    if(group) return group;
    // Dashed, fill-less zone outlines (no fill colour, neutral grey stroke).
    group = L.geoJSON(ZONES, {
      style: function(){ return {color:'#444', weight:2.5, opacity:.85, dashArray:'7 6', fill:false}; },
      onEachFeature: function(f, layer){
        var z = (f.properties && f.properties.zone) || '';
        layer.bindTooltip('HSL ' + z + ' 区', {sticky:true, className:'hsl-zone-label'});
      }
    });
    return group;
  }

  function toggle(btn){
    if(typeof map === 'undefined') return;
    on = !on;
    if(on){ ensureGroup().addTo(map); } else if(group){ map.removeLayer(group); }
    btn.classList.toggle('active', on);
  }

  function build(){
    var host = document.getElementById('viewControls');
    if(!host) return false;
    if(document.getElementById('zoneToggleBtn')) return true;
    var b = document.createElement('button');
    b.id = 'zoneToggleBtn';
    b.className = 'vc-btn';
    b.textContent = '③ HSL 票价区界（A/B/C/D）';
    b.addEventListener('click', function(){ toggle(b); });
    host.appendChild(b);
    return true;
  }

  function tryBuild(){ try { return build(); } catch(e){ return false; } }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', tryBuild);
  else tryBuild();
  [300, 900, 1800, 3500].forEach(function(ms){ setTimeout(tryBuild, ms); });
})();
</script>'''.replace('__ZONES_GEOJSON__', data_literal)

if '</body></html>' in text:
    text = text.replace('</body></html>', js + chr(10) + '</body></html>', 1)
elif '</body>' in text:
    text = text.replace('</body>', js + chr(10) + '</body>', 1)
else:
    text = text + chr(10) + js

index.write_text(text, encoding='utf-8')
print('Done: HSL zone boundaries now use official geometry (%d zones) + toggle.'
      % len(zones['features']))
print('Cached at offline/data/hsl_zones.geojson; backup index_before_hsl_zone_boundaries.html')
