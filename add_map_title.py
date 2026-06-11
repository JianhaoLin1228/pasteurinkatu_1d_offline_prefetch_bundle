#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Add an upper-left map title to offline/index.html.

Places "Viikki Campus附近的公交图" in the top-left corner, pushes the line
control panel just below it, and relocates the Leaflet zoom control to the
bottom-right so nothing overlaps. The title text is also registered in the
language controller, so EN/FI/CN switching translates it.

Idempotent: re-running replaces the injected block in place.
"""
from pathlib import Path

root = Path(__file__).resolve().parent
offline = root / 'offline'
index = offline / 'index.html'
if not index.exists():
    raise SystemExit('Missing offline/index.html')

text = index.read_text(encoding='utf-8')
backup = offline / 'index_before_map_title.html'
if not backup.exists():
    backup.write_text(text, encoding='utf-8')

script_id = 'map-title-final'
for marker in ["<script id='" + script_id + "'>", '<script id="' + script_id + '">']:
    while marker in text:
        before, rest = text.split(marker, 1)
        text = before + (rest.split('</script>', 1)[1] if '</script>' in rest else '')

css = '''
/* Upper-left map title; push the line panel below it. */
#mapTitle{
  position:absolute; top:12px; left:12px; z-index:1150;
  background:rgba(255,255,255,.96); border:1px solid #d0d7de; border-radius:12px;
  padding:8px 16px; font-size:16px; font-weight:700; color:#1f2328;
  box-shadow:0 6px 20px rgba(0,0,0,.18); max-width:calc(100vw - 24px);
  font-family:system-ui,-apple-system,'Segoe UI',sans-serif;
}
#lineControlPanel{ top:62px !important; }
'''
if 'Upper-left map title' not in text:
    if '</style>' in text:
        text = text.replace('</style>', css + '</style>', 1)
    elif '</head>' in text:
        text = text.replace('</head>', '<style>' + css + '</style></head>', 1)
    else:
        text = '<style>' + css + '</style>' + chr(10) + text

js = '''<script id="map-title-final">
(function(){
  function build(){
    if(!document.body) return false;
    var old = document.getElementById('mapTitle');
    if(old) old.remove();
    var t = document.createElement('div');
    t.id = 'mapTitle';
    t.textContent = 'Viikki Campus附近的公交图';
    document.body.appendChild(t);
    // Free the upper-left corner for the title.
    try {
      if(typeof map !== 'undefined' && map.zoomControl && map.zoomControl.setPosition){
        map.zoomControl.setPosition('bottomright');
      }
    } catch(e){}
    return true;
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', build);
  else build();
  [300, 1200, 3000].forEach(function(ms){ setTimeout(build, ms); });
})();
</script>'''

if '</body></html>' in text:
    text = text.replace('</body></html>', js + chr(10) + '</body></html>', 1)
elif '</body>' in text:
    text = text.replace('</body>', js + chr(10) + '</body>', 1)
else:
    text = text + chr(10) + js

index.write_text(text, encoding='utf-8')
print('Done: added upper-left map title; zoom control moved to bottom-right.')
print('Backup saved as offline/index_before_map_title.html')
