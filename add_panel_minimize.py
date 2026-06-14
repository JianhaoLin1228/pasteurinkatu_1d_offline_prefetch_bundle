#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Give every control panel a minimize / expand (–/+) header button.

The left line-control panel already has its own collapse (.lcp-collapse), so
this adds a matching one to the panels that lacked it: the view-control buttons
(#viewControls) and the two right-side Leaflet controls (basemap + commute). A
small header with a label and a –/+ button is prepended to each; collapsing
hides everything but the header, leaving a compact labelled pill.

(The language bar #langControl is intentionally left out: the language
controller rebuilds/translates every button inside it, which fights an injected
toggle, and it is a tiny switcher rather than a data panel.)

Idempotent: re-running replaces the injected block in place.
"""
from pathlib import Path

root = Path(__file__).resolve().parent
offline = root / 'offline'
index = offline / 'index.html'
if not index.exists():
    raise SystemExit('Missing offline/index.html')

text = index.read_text(encoding='utf-8')
backup = offline / 'index_before_panel_minimize.html'
if not backup.exists():
    backup.write_text(text, encoding='utf-8')

script_id = 'panel-minimize-final'
for marker in ["<script id='" + script_id + "'>", '<script id="' + script_id + '">']:
    while marker in text:
        before, rest = text.split(marker, 1)
        text = before + (rest.split('</script>', 1)[1] if '</script>' in rest else '')

css = '''
/* Minimize/expand header added to control panels lacking their own collapse. */
.pmin-head{ display:flex; align-items:center; justify-content:space-between; gap:10px;
  flex:0 0 100%; width:100%; box-sizing:border-box; margin:0 0 6px; padding:0 0 5px;
  border-bottom:1px solid rgba(0,0,0,.08); }
.pmin-label{ font:600 12px system-ui,-apple-system,'Segoe UI',sans-serif; color:#333;
  white-space:nowrap; }
.pmin-btn{ flex:0 0 auto; width:20px; height:20px; line-height:18px; text-align:center;
  font-size:15px; font-weight:700; color:#444; background:#fff; border:1px solid #c8c8c8;
  border-radius:6px; cursor:pointer; padding:0; }
.pmin-btn:hover{ background:#eee; }
.pmin-collapsed > *:not(.pmin-head){ display:none !important; }
.pmin-collapsed{ width:auto !important; min-width:0 !important; height:auto !important;
  max-height:none !important; min-height:0 !important; overflow:hidden !important; }
.pmin-collapsed .pmin-head{ margin-bottom:0; padding-bottom:0; border-bottom:none; }
'''
if 'Minimize/expand header added to control panels' not in text:
    if '</style>' in text:
        text = text.replace('</style>', css + '</style>', 1)
    elif '</head>' in text:
        text = text.replace('</head>', '<style>' + css + '</style></head>', 1)
    else:
        text = '<style>' + css + '</style>' + chr(10) + text

js = '''<script id="panel-minimize-final">
(function(){
  function addHead(panel, label){
    if(!panel || panel.getAttribute('data-pmin')) return;
    panel.setAttribute('data-pmin','1');
    var head = document.createElement('div');
    head.className = 'pmin-head';
    var lab = document.createElement('span');
    lab.className = 'pmin-label'; lab.textContent = label;
    var btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'pmin-btn'; btn.textContent = '–';
    btn.title = '最小化 / 展开';
    head.appendChild(lab); head.appendChild(btn);
    panel.insertBefore(head, panel.firstChild);
    btn.addEventListener('click', function(ev){
      ev.preventDefault(); ev.stopPropagation();
      var c = panel.classList.toggle('pmin-collapsed');
      btn.textContent = c ? '+' : '–';
    });
  }
  function attach(){
    try { addHead(document.querySelector('#viewControls'), '视图 / 图层'); } catch(e){}
    // the two right-side Leaflet controls, identified by their CONTENT so a
    // late-applied class can't mislabel them.
    try {
      document.querySelectorAll('.leaflet-top.leaflet-right .leaflet-control-layers').forEach(function(el){
        var t = el.textContent || '';
        if(/通勤|步行/.test(t)) addHead(el, '通勤圈 / 步行');
        else if(/底图|CartoDB|卫星|矢量/.test(t)) addHead(el, '底图');
      });
    } catch(e){}
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', attach);
  else attach();
  // panels are built by other injected scripts up to ~3.5s after load.
  [200, 600, 1200, 2200, 3600, 5200].forEach(function(ms){ setTimeout(attach, ms); });
})();
</script>'''

if '</body></html>' in text:
    text = text.replace('</body></html>', js + chr(10) + '</body></html>', 1)
elif '</body>' in text:
    text = text.replace('</body>', js + chr(10) + '</body>', 1)
else:
    text = text + chr(10) + js

index.write_text(text, encoding='utf-8')
print('Done: minimize/expand buttons added to viewControls, basemap and commute panels.')
print('Backup saved as offline/index_before_panel_minimize.html')
