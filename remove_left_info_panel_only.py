#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pathlib import Path

root = Path(__file__).resolve().parent
offline = root / 'offline'
index = offline / 'index.html'
if not index.exists():
    raise SystemExit('Missing offline/index.html')

text = index.read_text(encoding='utf-8')
backup = offline / 'index_before_remove_left_info_panel_only.html'
if not backup.exists():
    backup.write_text(text, encoding='utf-8')

script_id = 'remove-left-info-panel-only-final'
for marker in ["<script id='" + script_id + "'>", '<script id="' + script_id + '">']:
    while marker in text:
        before, rest = text.split(marker, 1)
        text = before + (rest.split('</script>', 1)[1] if '</script>' in rest else '')

css = '''
/* Remove only the custom left information panel. Do not touch Leaflet layer controls. */
#panel,
#togglePanel,
#bottomInfoPanel,
#bottomInfoToggle {
  display: none !important;
  visibility: hidden !important;
  pointer-events: none !important;
}
'''
if 'Remove only the custom left information panel' not in text:
    if '</style>' in text:
        text = text.replace('</style>', css + '</style>', 1)
    elif '</head>' in text:
        text = text.replace('</head>', '<style>' + css + '</style></head>', 1)
    else:
        text = '<style>' + css + '</style>' + chr(10) + text

js = '''<script id="remove-left-info-panel-only-final">
(function(){
  function removeLeftInfoPanelOnly(){
    ['panel','togglePanel','bottomInfoPanel','bottomInfoToggle'].forEach(function(id){
      var el = document.getElementById(id);
      if(el) el.remove();
    });
    if(typeof map !== 'undefined' && map.invalidateSize){
      setTimeout(function(){ map.invalidateSize(); }, 100);
    }
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', removeLeftInfoPanelOnly);
  else removeLeftInfoPanelOnly();
  setTimeout(removeLeftInfoPanelOnly, 200);
  setTimeout(removeLeftInfoPanelOnly, 800);
  setTimeout(removeLeftInfoPanelOnly, 1800);
})();
</script>'''

if '</body></html>' in text:
    text = text.replace('</body></html>', js + chr(10) + '</body></html>', 1)
elif '</body>' in text:
    text = text.replace('</body>', js + chr(10) + '</body>', 1)
else:
    text = text + chr(10) + js

index.write_text(text, encoding='utf-8')
print('Done: removed only the custom left information panel. Leaflet layer-control boxes were not changed.')
print('Backup saved as offline/index_before_remove_left_info_panel_only.html')
