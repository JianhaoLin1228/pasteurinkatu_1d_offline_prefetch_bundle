#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inject a left-hand panel that toggles each HSL transit line on/off.

Each route is its own L.layerGroup stored in the global `layers` object
(keyed by route_short_name) in offline/index.html. This panel lists every
line with a colored badge + checkbox and adds/removes its layer group from
the map. Idempotent: re-running replaces the injected block in place.
"""
from pathlib import Path

root = Path(__file__).resolve().parent
offline = root / 'offline'
index = offline / 'index.html'
if not index.exists():
    raise SystemExit('Missing offline/index.html')

text = index.read_text(encoding='utf-8')
backup = offline / 'index_before_line_control_panel.html'
if not backup.exists():
    backup.write_text(text, encoding='utf-8')

script_id = 'line-control-panel-final'
for marker in ["<script id='" + script_id + "'>", '<script id="' + script_id + '">']:
    while marker in text:
        before, rest = text.split(marker, 1)
        text = before + (rest.split('</script>', 1)[1] if '</script>' in rest else '')

css = '''
/* Left-hand transit line control panel. */
#lineControlPanel{
  position:absolute; top:84px; left:12px; z-index:1200;
  width:248px; max-width:calc(100vw - 24px); max-height:calc(100vh - 110px);
  display:flex; flex-direction:column;
  background:rgba(255,255,255,.97); border:1px solid #d0d7de; border-radius:14px;
  box-shadow:0 8px 28px rgba(0,0,0,.18); font-family:system-ui,-apple-system,'Segoe UI',sans-serif;
  overflow:hidden;
}
#lineControlPanel .lcp-head{
  display:flex; align-items:center; gap:8px; padding:10px 12px; border-bottom:1px solid #eaecef;
}
#lineControlPanel .lcp-title{ font-size:14px; font-weight:600; flex:1; }
#lineControlPanel .lcp-collapse{
  border:none; background:#f6f8fa; border-radius:8px; cursor:pointer;
  width:24px; height:24px; font-size:15px; line-height:1; color:#57606a;
}
#lineControlPanel .lcp-all{
  display:flex; align-items:center; gap:6px; padding:8px 12px;
  font-size:12px; color:#57606a; border-bottom:1px solid #eaecef; cursor:pointer;
}
#lineControlPanel .lcp-body{ overflow:auto; padding:4px 6px 8px; }
#lineControlPanel .lcp-row{
  display:flex; align-items:center; gap:8px; padding:5px 8px; border-radius:8px; cursor:pointer;
}
#lineControlPanel .lcp-row:hover{ background:#f6f8fa; }
#lineControlPanel .lcp-badge{
  display:inline-block; width:22px; height:5px; border-radius:5px; flex:0 0 auto;
}
#lineControlPanel .lcp-sn{ font-size:13px; font-weight:600; min-width:34px; }
#lineControlPanel .lcp-long{
  font-size:11px; color:#57606a; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; flex:1;
}
#lineControlPanel.lcp-collapsed .lcp-body,
#lineControlPanel.lcp-collapsed .lcp-all{ display:none; }
#lineControlPanel input[type="checkbox"]{ cursor:pointer; }
'''
if 'Left-hand transit line control panel.' not in text:
    if '</style>' in text:
        text = text.replace('</style>', css + '</style>', 1)
    elif '</head>' in text:
        text = text.replace('</head>', '<style>' + css + '</style></head>', 1)
    else:
        text = '<style>' + css + '</style>' + chr(10) + text

js = '''<script id="line-control-panel-final">
(function(){
  function lineKey(sn){
    var m = String(sn).match(/^(\\d+)(.*)$/);
    return m ? [parseInt(m[1],10), m[2]] : [Number.MAX_SAFE_INTEGER, String(sn)];
  }

  function collectLines(){
    // Source of truth for colors/long names is ROUTES_GEOJSON; the live
    // toggle target is the global `layers` group keyed by short name.
    var info = {};
    try {
      (ROUTES_GEOJSON.features || []).forEach(function(f){
        var p = f.properties || {};
        var sn = p.route_short_name;
        if(sn == null || info[sn]) return;
        info[sn] = { sn: sn, color: p.color || '#333', long: p.route_long_name || '' };
      });
    } catch(e){}
    return Object.keys(layers).filter(function(sn){ return !!layers[sn]; })
      .map(function(sn){ return info[sn] || { sn: sn, color:'#333', long:'' }; })
      .sort(function(a,b){
        var ka = lineKey(a.sn), kb = lineKey(b.sn);
        return ka[0] - kb[0] || String(ka[1]).localeCompare(String(kb[1]));
      });
  }

  function build(){
    if(typeof map === 'undefined' || typeof layers === 'undefined') return false;
    var lines = collectLines();
    if(!lines.length) return false;

    var existing = document.getElementById('lineControlPanel');
    if(existing) existing.remove();

    var panel = document.createElement('div');
    panel.id = 'lineControlPanel';

    var head = document.createElement('div');
    head.className = 'lcp-head';
    head.innerHTML = '<span class="lcp-title">线路显示控制</span>'
      + '<button class="lcp-collapse" title="折叠/展开">–</button>';
    panel.appendChild(head);

    var allRow = document.createElement('label');
    allRow.className = 'lcp-all';
    allRow.innerHTML = '<input type="checkbox" class="lcp-all-input"> 全部显示 / 全部隐藏';
    panel.appendChild(allRow);
    var allInput = allRow.querySelector('input');

    var body = document.createElement('div');
    body.className = 'lcp-body';
    panel.appendChild(body);

    var rowInputs = [];
    function syncAll(){
      var on = rowInputs.filter(function(i){ return i.checked; }).length;
      allInput.checked = on === rowInputs.length;
      allInput.indeterminate = on > 0 && on < rowInputs.length;
    }

    lines.forEach(function(L0){
      var sn = L0.sn, grp = layers[sn];
      var row = document.createElement('label');
      row.className = 'lcp-row';
      row.title = sn + ' ' + L0.long;
      var checked = map.hasLayer(grp);
      row.innerHTML = '<input type="checkbox"' + (checked ? ' checked' : '') + '>'
        + '<span class="lcp-badge" style="background:' + L0.color + '"></span>'
        + '<span class="lcp-sn">' + sn + '</span>'
        + '<span class="lcp-long">' + (L0.long || '') + '</span>';
      var input = row.querySelector('input');
      rowInputs.push(input);
      input.addEventListener('change', function(){
        if(input.checked){ grp.addTo(map); } else { map.removeLayer(grp); }
        syncAll();
      });
      body.appendChild(row);
    });

    allInput.addEventListener('change', function(){
      var on = allInput.checked;
      rowInputs.forEach(function(input, idx){
        if(input.checked !== on){
          input.checked = on;
          var grp = layers[lines[idx].sn];
          if(on){ grp.addTo(map); } else { map.removeLayer(grp); }
        }
      });
      allInput.indeterminate = false;
    });

    head.querySelector('.lcp-collapse').addEventListener('click', function(){
      var c = panel.classList.toggle('lcp-collapsed');
      this.textContent = c ? '+' : '–';
    });

    syncAll();
    document.body.appendChild(panel);
    return true;
  }

  function tryBuild(){ try { return build(); } catch(e){ return false; } }

  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', tryBuild);
  else tryBuild();
  // `layers` is populated by the main map script; retry until it exists.
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
print('Done: added left-hand line control panel (toggle each transit line on/off).')
print('Backup saved as offline/index_before_line_control_panel.html')
