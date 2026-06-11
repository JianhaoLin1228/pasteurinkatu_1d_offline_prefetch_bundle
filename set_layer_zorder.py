#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Enforce a deterministic stacking order on offline/index.html.

Desired top -> bottom:
    transit lines (top)
    10 / 15 / 20 / 30 / 40 minute commute circles (40 at the bottom)

The commute groups are local to another injected script, so we can't reference
them; instead we re-establish order by walking the live map layers. Commute
isochrones are L.Polygon with one of five known stroke colors, which separates
them from the walk/reference rings (L.Circle) and the transit lines (plain
L.Polyline). Re-applied on every layeradd so toggling never breaks the order.

Idempotent: re-running replaces the injected block in place.
"""
from pathlib import Path

root = Path(__file__).resolve().parent
offline = root / 'offline'
index = offline / 'index.html'
if not index.exists():
    raise SystemExit('Missing offline/index.html')

text = index.read_text(encoding='utf-8')
backup = offline / 'index_before_layer_zorder.html'
if not backup.exists():
    backup.write_text(text, encoding='utf-8')

script_id = 'layer-zorder-commute-final'
for marker in ["<script id='" + script_id + "'>", '<script id="' + script_id + '">']:
    while marker in text:
        before, rest = text.split(marker, 1)
        text = before + (rest.split('</script>', 1)[1] if '</script>' in rest else '')

js = '''<script id="layer-zorder-commute-final">
(function(){
  // Stroke colors assigned per commute minute in the layer-reset script.
  var COMMUTE_COLORS = {'#22c55e':10, '#0f766e':15, '#2563eb':20, '#f97316':30, '#7c3aed':40};
  // Bring these to front in turn; the last one (10) ends highest, 40 lowest.
  var BOTTOM_TO_TOP = [40, 30, 20, 15, 10];

  function commuteBuckets(){
    var b = {10:[], 15:[], 20:[], 30:[], 40:[]};
    map.eachLayer(function(l){
      // Commute isochrones are polygons; walk/reference rings are L.Circle and
      // transit lines are plain L.Polyline, so neither is matched here.
      if(l instanceof L.Polygon && l.options && l.bringToFront){
        var m = COMMUTE_COLORS[(l.options.color || '').toLowerCase()];
        if(m != null) b[m].push(l);
      }
    });
    return b;
  }

  function applyZOrder(){
    if(typeof map === 'undefined') return;
    var b = commuteBuckets();
    BOTTOM_TO_TOP.forEach(function(m){
      b[m].forEach(function(l){ try { l.bringToFront(); } catch(e){} });
    });
    // Transit lines stay on top of every commute circle.
    try {
      if(typeof layers !== 'undefined'){
        Object.keys(layers).forEach(function(sn){
          var g = layers[sn];
          if(g && g.eachLayer) g.eachLayer(function(l){
            if(l.bringToFront){ try { l.bringToFront(); } catch(e){} }
          });
        });
      }
    } catch(e){}
  }

  var pending = null;
  function schedule(){
    if(pending) return;
    pending = setTimeout(function(){ pending = null; applyZOrder(); }, 80);
  }

  function init(){
    if(typeof map === 'undefined') return false;
    if(!map.__zorderBound){
      map.__zorderBound = true;
      map.on('layeradd overlayadd', schedule);
    }
    applyZOrder();
    return true;
  }

  function tryInit(){ try { return init(); } catch(e){ return false; } }

  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', tryInit);
  else tryInit();
  // Commute layers are toggled by async clicks up to ~3500ms; re-apply after.
  [300, 1000, 2000, 4000].forEach(function(ms){ setTimeout(applyZOrder, ms); });
})();
</script>'''

if '</body></html>' in text:
    text = text.replace('</body></html>', js + chr(10) + '</body></html>', 1)
elif '</body>' in text:
    text = text.replace('</body>', js + chr(10) + '</body>', 1)
else:
    text = text + chr(10) + js

index.write_text(text, encoding='utf-8')
print('Done: commute circles ordered 10(top)->40(bottom); transit lines kept topmost.')
print('Backup saved as offline/index_before_layer_zorder.html')
