#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inject two lower-left "best view" buttons into offline/index.html.

  (1) fit the map to all transit lines (reuses the global `allBounds`,
      falling back to recomputing from the `layers` route groups);
  (2) frame the University of Helsinki Viikki campus.

Idempotent: re-running replaces the injected block in place.
"""
from pathlib import Path

root = Path(__file__).resolve().parent
offline = root / 'offline'
index = offline / 'index.html'
if not index.exists():
    raise SystemExit('Missing offline/index.html')

text = index.read_text(encoding='utf-8')
backup = offline / 'index_before_view_control_buttons.html'
if not backup.exists():
    backup.write_text(text, encoding='utf-8')

script_id = 'view-control-buttons-final'
for marker in ["<script id='" + script_id + "'>", '<script id="' + script_id + '">']:
    while marker in text:
        before, rest = text.split(marker, 1)
        text = before + (rest.split('</script>', 1)[1] if '</script>' in rest else '')

css = '''
/* Lower-left best-view buttons. */
#viewControls{
  position:absolute; left:12px; bottom:18px; z-index:1300;
  display:flex; flex-direction:column; gap:8px;
  font-family:system-ui,-apple-system,'Segoe UI',sans-serif;
}
#viewControls .vc-btn{
  appearance:none; border:1px solid #d0d7de; border-radius:12px; cursor:pointer;
  background:rgba(255,255,255,.97); color:#1f2328; font-size:13px; font-weight:600;
  padding:9px 14px; text-align:left; box-shadow:0 6px 20px rgba(0,0,0,.18);
}
#viewControls .vc-btn:hover{ background:#f3f6f9; }
#viewControls .vc-btn:active{ transform:translateY(1px); }
'''
if 'Lower-left best-view buttons.' not in text:
    if '</style>' in text:
        text = text.replace('</style>', css + '</style>', 1)
    elif '</head>' in text:
        text = text.replace('</head>', '<style>' + css + '</style></head>', 1)
    else:
        text = '<style>' + css + '</style>' + chr(10) + text

js = '''<script id="view-control-buttons-final">
(function(){
  // Bounding box framing the University of Helsinki Viikki campus.
  var VIIKKI = L.latLngBounds([[60.2230, 25.0090], [60.2315, 25.0290]]);

  function allLinesBounds(){
    try {
      if(typeof allBounds !== 'undefined' && allBounds && allBounds.isValid()) return allBounds;
    } catch(e){}
    var b = L.latLngBounds([]);
    try {
      Object.keys(layers).forEach(function(sn){
        var g = layers[sn];
        if(g && g.eachLayer) g.eachLayer(function(l){ if(l.getBounds) b.extend(l.getBounds()); });
      });
    } catch(e){}
    return b;
  }

  function build(){
    if(typeof map === 'undefined') return false;
    var old = document.getElementById('viewControls');
    if(old) old.remove();

    var box = document.createElement('div');
    box.id = 'viewControls';

    var b1 = document.createElement('button');
    b1.className = 'vc-btn';
    b1.textContent = '① 全部线路最佳视野';
    b1.addEventListener('click', function(){
      var b = allLinesBounds();
      if(b && b.isValid()) map.fitBounds(b.pad(0.05));
    });

    var b2 = document.createElement('button');
    b2.className = 'vc-btn';
    b2.textContent = '② Viikki 校区最佳视野';
    b2.addEventListener('click', function(){ map.fitBounds(VIIKKI); });

    box.appendChild(b1);
    box.appendChild(b2);
    document.body.appendChild(box);
    return true;
  }

  function tryBuild(){ try { return build(); } catch(e){ return false; } }

  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', tryBuild);
  else tryBuild();
  [200, 700, 1500, 3000].forEach(function(ms){ setTimeout(tryBuild, ms); });
})();
</script>'''

if '</body></html>' in text:
    text = text.replace('</body></html>', js + chr(10) + '</body></html>', 1)
elif '</body>' in text:
    text = text.replace('</body>', js + chr(10) + '</body>', 1)
else:
    text = text + chr(10) + js

index.write_text(text, encoding='utf-8')
print('Done: added two lower-left best-view buttons (all lines / Viikki campus).')
print('Backup saved as offline/index_before_view_control_buttons.html')
