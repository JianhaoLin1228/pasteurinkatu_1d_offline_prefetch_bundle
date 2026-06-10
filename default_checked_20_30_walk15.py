#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pathlib import Path

root = Path(__file__).resolve().parent
offline = root / 'offline'
index = offline / 'index.html'
if not index.exists():
    raise SystemExit('Missing offline/index.html')

text = index.read_text(encoding='utf-8')
backup = offline / 'index_before_default_checked_20_30_walk15.html'
if not backup.exists():
    backup.write_text(text, encoding='utf-8')

script_id = 'default-checked-20-30-walk15-final'
for marker in ["<script id='" + script_id + "'>", '<script id="' + script_id + '">']:
    while marker in text:
        before, rest = text.split(marker, 1)
        text = before + (rest.split('</script>', 1)[1] if '</script>' in rest else '')

js = '''<script id="default-checked-20-30-walk15-final">
(function(){
  const DEFAULT_ON = [
    '20分钟通勤圈（GTFS+等候）',
    '30分钟通勤圈（GTFS+等候）',
    '15分钟步行圈'
  ];
  const DEFAULT_ON_COMPACT = new Set(DEFAULT_ON.map(s => s.replace(/\s+/g,'')));

  function labelText(label){
    return (label.innerText || label.textContent || '').replace(/\s+/g,'').trim();
  }

  function setDefaultChecked(){
    if(typeof map === 'undefined') return;

    document.querySelectorAll('.leaflet-control-layers-overlays label').forEach(label => {
      const txt = labelText(label);
      const input = label.querySelector('input[type="checkbox"]');
      if(!input) return;

      const shouldBeOn = DEFAULT_ON_COMPACT.has(txt);
      if(input.checked !== shouldBeOn) {
        // Use click so Leaflet actually adds/removes the linked layer group.
        input.click();
      }
    });
  }

  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', setDefaultChecked);
  else setDefaultChecked();

  // Layer controls may be created by later injected scripts; run a few times.
  setTimeout(setDefaultChecked, 250);
  setTimeout(setDefaultChecked, 900);
  setTimeout(setDefaultChecked, 1800);
  setTimeout(setDefaultChecked, 3500);
})();
</script>'''

if '</body></html>' in text:
    text = text.replace('</body></html>', js + chr(10) + '</body></html>', 1)
elif '</body>' in text:
    text = text.replace('</body>', js + chr(10) + '</body>', 1)
else:
    text = text + chr(10) + js

index.write_text(text, encoding='utf-8')
print('Done: default checked layers are 20 min commute, 30 min commute, and 15 min walking only.')
print('Backup saved as offline/index_before_default_checked_20_30_walk15.html')
