#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inject a lower-left EN / FI / CN language switcher into offline/index.html.

UI text is authored in Chinese. The switcher translates the known user-facing
strings (layer-control labels, base maps, the line panel, the view buttons and
the title buttons) by walking text nodes and swapping any of the three known
forms to the selected language. A debounced MutationObserver re-applies the
current language so late-built / rebuilt controls stay translated. Choice is
remembered in localStorage. Idempotent: re-running replaces the block in place.
"""
from pathlib import Path

root = Path(__file__).resolve().parent
offline = root / 'offline'
index = offline / 'index.html'
if not index.exists():
    raise SystemExit('Missing offline/index.html')

text = index.read_text(encoding='utf-8')
backup = offline / 'index_before_language_controller.html'
if not backup.exists():
    backup.write_text(text, encoding='utf-8')

script_id = 'language-controller-final'
for marker in ["<script id='" + script_id + "'>", '<script id="' + script_id + '">']:
    while marker in text:
        before, rest = text.split(marker, 1)
        text = before + (rest.split('</script>', 1)[1] if '</script>' in rest else '')

css = '''
/* Lower-left language switcher; lift the view buttons above it. */
#viewControls{ bottom:64px !important; }
#langControl{
  position:absolute; left:12px; bottom:18px; z-index:1300;
  display:flex; gap:0; background:rgba(255,255,255,.97);
  border:1px solid #d0d7de; border-radius:12px; overflow:hidden;
  box-shadow:0 6px 20px rgba(0,0,0,.18);
  font-family:system-ui,-apple-system,'Segoe UI',sans-serif;
}
#langControl button{
  appearance:none; border:none; background:transparent; cursor:pointer;
  padding:7px 13px; font-size:13px; font-weight:600; color:#57606a;
  border-right:1px solid #eaecef;
}
#langControl button:last-child{ border-right:none; }
#langControl button:hover{ background:#f3f6f9; }
#langControl button.active{ background:#0969da; color:#fff; }
'''
if 'Lower-left language switcher' not in text:
    if '</style>' in text:
        text = text.replace('</style>', css + '</style>', 1)
    elif '</head>' in text:
        text = text.replace('</head>', '<style>' + css + '</style></head>', 1)
    else:
        text = '<style>' + css + '</style>' + chr(10) + text

js = r'''<script id="language-controller-final">
(function(){
  // [cn, en, fi] for every translatable UI string.
  var ENTRIES = [
    ['Viikki Campus附近的公交图', 'Transit map near Viikki Campus', 'Joukkoliikennekartta Viikin kampuksen lähellä'],
    ['10分钟通勤圈（GTFS+等候）', '10-min commute (GTFS + waiting)', '10 min työmatka (GTFS + odotus)'],
    ['15分钟通勤圈（GTFS+等候）', '15-min commute (GTFS + waiting)', '15 min työmatka (GTFS + odotus)'],
    ['20分钟通勤圈（GTFS+等候）', '20-min commute (GTFS + waiting)', '20 min työmatka (GTFS + odotus)'],
    ['30分钟通勤圈（GTFS+等候）', '30-min commute (GTFS + waiting)', '30 min työmatka (GTFS + odotus)'],
    ['40分钟通勤圈（GTFS+等候）', '40-min commute (GTFS + waiting)', '40 min työmatka (GTFS + odotus)'],
    ['10分钟步行圈', '10-min walking', '10 min kävely'],
    ['15分钟步行圈', '15-min walking', '15 min kävely'],
    ['CartoDB 浅色真实底图', 'CartoDB light basemap', 'CartoDB vaalea taustakartta'],
    ['Esri 卫星影像', 'Esri satellite imagery', 'Esri-satelliittikuva'],
    ['无底图/纯矢量', 'No basemap / vectors only', 'Ei taustakarttaa / vain vektorit'],
    ['线路显示控制', 'Transit lines', 'Linjat'],
    ['全部显示 / 全部隐藏', 'Show all / hide all', 'Näytä / piilota kaikki'],
    ['① 全部线路最佳视野', '① Fit all lines', '① Sovita kaikki linjat'],
    ['② Viikki 校区最佳视野', '② Viikki campus view', '② Viikin kampus'],
    ['③ HSL 票价区界（A/B/C/D）', '③ HSL fare zones (A/B/C/D)', '③ HSL-vyöhykkeet (A/B/C/D)'],
    ['④ HOAS 房源（价格）', '④ HOAS housing (prices)', '④ HOAS-asunnot (hinnat)'],
    ['⑤ HYS 房源（Domo）', '⑤ HYS housing (Domo)', '⑤ HYS-asunnot (Domo)'],
    ['缩放到全部线路', 'Zoom to all lines', 'Lähennä kaikkiin linjoihin'],
    ['缩放到 Pasteurinkatu 1D', 'Zoom to Pasteurinkatu 1D', 'Lähennä: Pasteurinkatu 1D']
  ];
  var IDX = {cn:0, en:1, fi:2};

  // Map every known form -> its entry, for two-way switching.
  var LOOKUP = {};
  ENTRIES.forEach(function(e){ e.forEach(function(form){ LOOKUP[form] = e; }); });

  var current = (function(){ try { return localStorage.getItem('mapUiLang') || 'cn'; } catch(e){ return 'cn'; } })();
  var observer = null;

  function translate(lang){
    var col = IDX[lang]; if(col == null) return;
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
    var nodes = [], n;
    while((n = walker.nextNode())) nodes.push(n);
    nodes.forEach(function(node){
      var key = node.nodeValue.trim();
      if(!key) return;
      var entry = LOOKUP[key];
      if(!entry) return;
      var target = entry[col];
      var next = node.nodeValue.replace(key, target);
      if(next !== node.nodeValue) node.nodeValue = next;
    });
  }

  function apply(lang){
    if(observer) observer.disconnect();
    try { translate(lang); } catch(e){}
    if(observer) observer.observe(document.body, {childList:true, subtree:true, characterData:true});
  }

  function highlight(lang){
    var box = document.getElementById('langControl');
    if(!box) return;
    box.querySelectorAll('button').forEach(function(b){
      b.classList.toggle('active', b.getAttribute('data-lang') === lang);
    });
  }

  function setLang(lang){
    current = lang;
    try { localStorage.setItem('mapUiLang', lang); } catch(e){}
    highlight(lang);
    apply(lang);
  }

  function build(){
    if(document.getElementById('langControl')) return;
    var box = document.createElement('div');
    box.id = 'langControl';
    [['en','EN'], ['fi','FI'], ['cn','中文']].forEach(function(pair){
      var b = document.createElement('button');
      b.setAttribute('data-lang', pair[0]);
      b.textContent = pair[1];
      b.addEventListener('click', function(){ setLang(pair[0]); });
      box.appendChild(b);
    });
    document.body.appendChild(box);

    // Re-apply current language whenever controls are (re)built.
    var pending = null;
    observer = new MutationObserver(function(){
      if(current === 'cn') return;          // source is already Chinese
      if(pending) return;
      pending = setTimeout(function(){ pending = null; apply(current); }, 150);
    });
    observer.observe(document.body, {childList:true, subtree:true, characterData:true});

    highlight(current);
    if(current !== 'cn') apply(current);
  }

  function init(){ try { build(); } catch(e){} }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
  // Controls are built asynchronously; re-apply once they exist.
  [400, 1200, 2500, 4500].forEach(function(ms){ setTimeout(function(){ if(current !== 'cn') apply(current); }, ms); });
})();
</script>'''

if '</body></html>' in text:
    text = text.replace('</body></html>', js + chr(10) + '</body></html>', 1)
elif '</body>' in text:
    text = text.replace('</body>', js + chr(10) + '</body>', 1)
else:
    text = text + chr(10) + js

index.write_text(text, encoding='utf-8')
print('Done: added lower-left EN / FI / CN language switcher.')
print('Backup saved as offline/index_before_language_controller.html')
