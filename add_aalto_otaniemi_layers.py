#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inject campus-aware commute + listing layers into offline/index.html.

Replaces the old aalto-otaniemi-layers-final, hoas-listings-final, and
hys-listings-final blocks with a single campus-aware-layers-final block that:

  - Adds a campus selector (Viikki / Aalto Otaniemi) driving commute circles,
    popup commute times, and map view simultaneously.
  - Shows all HOAS/HYS listings (independent toggles); popup content adapts to
    the active campus (shows Aalto commute time when Aalto is selected).
  - Controls Aalto commute circles via threshold buttons (≤10…≤40 min) embedded
    in viewControls — no separate floating Leaflet panel.

Idempotent: re-running replaces the injected block in place.
Run build_aalto_otaniemi_commute.py first to generate the data files.
"""
import json
from pathlib import Path

root   = Path(__file__).resolve().parent
offline = root / 'offline'
data   = offline / 'data'
index  = offline / 'index.html'

if not index.exists():
    raise SystemExit('Missing offline/index.html')

for p in [
    data / 'commute_aalto_otaniemi_gtfs.geojson',
    data / 'hoas_listings_aalto_otaniemi.geojson',
    data / 'hys_listings_aalto_otaniemi.geojson',
]:
    if not p.exists():
        raise SystemExit(f'Missing {p}; run build_aalto_otaniemi_commute.py first')

commute = json.loads((data / 'commute_aalto_otaniemi_gtfs.geojson').read_text(encoding='utf-8'))
hoas    = json.loads((data / 'hoas_listings_aalto_otaniemi.geojson').read_text(encoding='utf-8'))
hys     = json.loads((data / 'hys_listings_aalto_otaniemi.geojson').read_text(encoding='utf-8'))

text = index.read_text(encoding='utf-8')

# ── Backup (first run only) ───────────────────────────────────────────────
backup = offline / 'index_before_campus_aware_layers.html'
if not backup.exists():
    backup.write_text(text, encoding='utf-8')

# ── Remove old script blocks that this script replaces ────────────────────
for script_id in [
    'campus-aware-layers-final',   # own previous run
    'aalto-otaniemi-layers-final', # old Aalto injection
    'hoas-listings-final',         # old HOAS injection (replaced here)
    'hys-listings-final',          # old HYS injection (replaced here)
]:
    for marker in [f"<script id='{script_id}'>", f'<script id="{script_id}">']:
        while marker in text:
            before, rest = text.split(marker, 1)
            text = before + (rest.split('</script>', 1)[1] if '</script>' in rest else '')

# ── CSS (injected once) ───────────────────────────────────────────────────
CSS_MARKER = '/* campus-aware-layers */'
css = f'''
{CSS_MARKER}
/* ── shared home markers ──────────────────────────────────────────── */
.hoas-home-wrap{{background:none;border:none;}}
.hoas-home{{
  width:26px;height:26px;line-height:26px;text-align:center;font-size:18px;
  background:#fff;border:2px solid #d62728;border-radius:50%;
  box-shadow:0 2px 6px rgba(0,0,0,.35);
}}
.hys-home{{
  width:26px;height:26px;line-height:26px;text-align:center;font-size:18px;
  background:#fff;border:2px solid #1f6feb;border-radius:50%;
  box-shadow:0 2px 6px rgba(0,0,0,.35);
}}
.hoas-popup b{{font-size:13px;}}
.hoas-popup .rent{{color:#d62728;font-weight:700;}}
.hoas-popup .condition{{color:#57606a;}}
.hoas-condition-filter{{display:flex;flex-wrap:wrap;gap:6px;margin-top:7px;}}
.hoas-condition-filter button{{min-height:28px;padding:4px 8px;border:1px solid #d0d7de;border-radius:7px;background:#fff;color:#24292f;font-size:11px;font-weight:650;cursor:pointer;}}
.hoas-condition-filter button.active{{background:#d62728;border-color:#d62728;color:#fff;}}
/* ── campus selector ──────────────────────────────────────────────── */
#campusSelector{{
  display:flex;align-items:center;flex-wrap:wrap;gap:4px;
  padding:6px 0 8px;border-bottom:1px solid #e1e4e8;margin-bottom:4px;
}}
.campus-label{{font-size:11px;color:#57606a;white-space:nowrap;margin-right:2px;}}
.campus-btn.campus-active{{background:#111827;color:#fff;border-color:#111827;}}
/* ── Aalto target marker ──────────────────────────────────────────── */
.aalto-target-icon{{
  width:28px;height:28px;line-height:28px;text-align:center;font-size:15px;
  font-weight:700;background:#111827;color:#fff;border:2px solid #fff;
  border-radius:50%;box-shadow:0 2px 7px rgba(0,0,0,.4);
}}
/* ── threshold controls ───────────────────────────────────────────── */
#aaltoThresholdCtrl{{
  display:flex;align-items:center;flex-wrap:wrap;gap:3px;
  padding:6px 0 2px;border-top:1px solid #e1e4e8;margin-top:4px;
}}
.thr-btn{{padding:2px 7px!important;font-size:11px!important;}}
.thr-btn.thr-active{{background:#7c3aed;color:#fff;border-color:#7c3aed;}}
/* ── viewControls active states ───────────────────────────────────── */
#viewControls .vc-btn.hoas-active{{background:#d62728;color:#fff;border-color:#d62728;}}
#viewControls .vc-btn.hys-active{{background:#1f6feb;color:#fff;border-color:#1f6feb;}}
'''
if CSS_MARKER not in text:
    if '</style>' in text:
        text = text.replace('</style>', css + '</style>', 1)
    elif '</head>' in text:
        text = text.replace('</head>', f'<style>{css}</style></head>', 1)
    else:
        text = f'<style>{css}</style>\n' + text

# ── JavaScript ────────────────────────────────────────────────────────────
js = r'''<script id="campus-aware-layers-final">
(function(){
'use strict';

// ── embedded data ──────────────────────────────────────────────────────────
var AALTO_COMMUTE = __COMMUTE__;
var HOAS_DATA     = __HOAS__;
var HYS_DATA      = __HYS__;

var THRESHOLDS    = [10, 15, 20, 30, 40];
var COLORS        = {10:'#22c55e',15:'#0f766e',20:'#2563eb',30:'#f97316',40:'#7c3aed'};
var AALTO_LL      = [60.1842, 24.8269];
var AALTO_BOUNDS  = L.latLngBounds([[60.162, 24.795], [60.210, 24.870]]);
var VIIKKI_LL     = [60.2245961, 25.014318];
var VIIKKI_ZOOM   = 14;

// ── global campus state ────────────────────────────────────────────────────
window.CAMPUS = 'viikki';

// ── Aalto commute circles ──────────────────────────────────────────────────
var aaltoGroups   = null;
var aaltoThreshold = 0;   // 0 = all hidden

function buildAaltoGroups(){
  if(aaltoGroups) return;
  aaltoGroups = {};
  THRESHOLDS.forEach(function(m){ aaltoGroups[m] = L.layerGroup(); });
  (AALTO_COMMUTE.features||[]).forEach(function(f){
    var p = f.properties||{}, m = Number(p.minutes);
    var layer = aaltoGroups[m];
    if(!layer || !f.geometry) return;
    var color = p.color || COLORS[m] || '#333';
    if(f.geometry.type==='Polygon'){
      var ll = f.geometry.coordinates[0].map(function(c){ return [c[1],c[0]]; });
      if(p.kind==='convex_hull_outline'){
        L.polygon(ll,{color:color,weight:m===40?3.5:3,fill:false,
          dashArray:m===40?'12 6':'8 6',opacity:.95})
         .bindPopup(m+' 分钟内可达 Aalto Otaniemi（早高峰最优出发）').addTo(layer);
      } else {
        L.polygon(ll,{color:color,weight:0,fillColor:color,
          fillOpacity:m===40?.065:.095,interactive:false}).addTo(layer);
      }
    } else if(f.geometry.type==='Point' && p.kind==='reachable_stop'){
      L.circleMarker([f.geometry.coordinates[1],f.geometry.coordinates[0]],
        {radius:2.5,color:color,fillColor:color,fillOpacity:.75,weight:1})
       .bindPopup('<b>≤'+m+' 分钟可达 Aalto</b><br>'+(p.stop_name||p.stop_id)
                  +'<br>站到校：'+p.arrival_min+' min').addTo(layer);
    }
  });
}

function applyThreshold(t){
  aaltoThreshold = t;
  buildAaltoGroups();
  THRESHOLDS.forEach(function(m){
    if(window.CAMPUS==='aalto' && m<=t){ aaltoGroups[m].addTo(map); }
    else { map.removeLayer(aaltoGroups[m]); }
  });
  // update button states
  THRESHOLDS.forEach(function(m){
    var b = document.getElementById('aaltoThr'+m);
    if(b) b.classList.toggle('thr-active', m<=t && t>0);
  });
}

// ── Aalto target pin ───────────────────────────────────────────────────────
var aaltoTargetAdded = false;
function addAaltoTarget(){
  if(aaltoTargetAdded) return;
  aaltoTargetAdded = true;
  var icon = L.divIcon({
    className:'',
    html:'<div class="aalto-target-icon">A</div>',
    iconSize:[28,28], iconAnchor:[14,14]
  });
  L.marker(AALTO_LL,{icon:icon,zIndexOffset:2000,riseOnHover:true})
   .bindPopup('<b>Aalto University Otaniemi</b><br>当前目标校区')
   .addTo(map);
}

// ── helpers ────────────────────────────────────────────────────────────────
function priceLine(p){
  if(p.min_rent==null) return '价格见链接';
  return p.min_rent===p.max_rent ? (p.min_rent+' €/kk')
       : (p.min_rent+'–'+p.max_rent+' €/kk');
}

function conditionLine(p){
  return p.condition ? ('<br><span class="condition">状况：'+p.condition+'</span>') : '';
}

// ── HOAS layer ─────────────────────────────────────────────────────────────
var hoasGroup=null, hoasOn=false, hoasCondition='all';

function conditionMatches(p){
  return hoasCondition==='all' || (hoasCondition==='__unknown__' ? !p.condition : (p.condition||'')===hoasCondition);
}

function syncConditionButtons(){
  document.querySelectorAll('#hoasConditionFilter button[data-condition]').forEach(function(b){
    b.classList.toggle('active', b.dataset.condition===hoasCondition);
  });
}

function setHoasCondition(condition){
  hoasCondition=condition;
  if(hoasGroup) buildHoasGroup();
  syncConditionButtons();
}

function hoasPopupHtml(p){
  var commute='';
  if(window.CAMPUS==='aalto'){
    if(p.aalto_otaniemi_min!=null){
      commute='<br>🚇 Aalto: <b>约 '+p.aalto_otaniemi_min+' min</b>';
      if(!p.aalto_otaniemi_40min) commute+=' (>40 min)';
    } else {
      commute='<br>🚇 Aalto: 超过 40 min';
    }
  }
  return '<div class="hoas-popup"><b>'+(p.address||'HOAS')+'</b>'
        +'<br><span class="rent">'+priceLine(p)+'</span>'
        +conditionLine(p)
        +commute
        +'<br><a href="'+p.url+'" target="_blank" rel="noopener">HOAS 房源页 →</a></div>';
}

function buildHoasGroup(){
  if(!hoasGroup){
    if(!map.getPane('hoasPane')){
      map.createPane('hoasPane');
      map.getPane('hoasPane').style.zIndex=650;
    }
    hoasGroup=L.layerGroup();
  }
  hoasGroup.clearLayers();
  var icon=L.divIcon({className:'hoas-home-wrap', html:'<div class="hoas-home">🏠</div>',iconSize:[26,26],iconAnchor:[13,13]});
  (HOAS_DATA.features||[]).forEach(function(f){
    var p=f.properties||{}, c=(f.geometry||{}).coordinates||[];
    if(c.length<2 || !conditionMatches(p)) return;
    var mk=L.marker([c[1],c[0]],{icon:icon,pane:'hoasPane',riseOnHover:true});
    mk.bindPopup(function(){ return hoasPopupHtml(p); });
    mk.bindTooltip(priceLine(p),{direction:'top'});
    mk.addTo(hoasGroup);
  });
  return hoasGroup;
}

function toggleHoas(btn){
  hoasOn=!hoasOn;
  if(hoasOn){ buildHoasGroup().addTo(map); } else if(hoasGroup){ map.removeLayer(hoasGroup); }
  btn.classList.toggle('hoas-active',hoasOn);
}

// ── HYS layer ──────────────────────────────────────────────────────────────
var hysGroup=null, hysOn=false;

function hysPopupHtml(p){
  var commute='';
  if(window.CAMPUS==='aalto'){
    if(p.aalto_otaniemi_min!=null){
      commute='<br>🚇 Aalto: <b>约 '+p.aalto_otaniemi_min+' min</b>';
      if(!p.aalto_otaniemi_40min) commute+=' (>40 min)';
    } else {
      commute='<br>🚇 Aalto: 超过 40 min';
    }
  }
  return '<div class="hoas-popup"><b>'+(p.name||p.address||'HYS')+'</b>'
        +'<br>HYS · <span class="rent">价格见 Domo</span>'
        +commute
        +'<br><a href="'+p.url+'" target="_blank" rel="noopener">HYS 房源页 →</a></div>';
}

function buildHysGroup(){
  if(hysGroup) return hysGroup;
  if(!map.getPane('hysPane')){
    map.createPane('hysPane');
    map.getPane('hysPane').style.zIndex=651;
  }
  var icon=L.divIcon({className:'hoas-home-wrap',
    html:'<div class="hys-home">🏠</div>',iconSize:[26,26],iconAnchor:[13,13]});
  hysGroup=L.layerGroup();
  (HYS_DATA.features||[]).forEach(function(f){
    var p=f.properties||{}, c=(f.geometry||{}).coordinates||[];
    if(c.length<2) return;
    var mk=L.marker([c[1],c[0]],{icon:icon,pane:'hysPane',riseOnHover:true});
    mk.bindPopup(function(){ return hysPopupHtml(p); });
    mk.bindTooltip(p.name||'HYS',{direction:'top'});
    mk.addTo(hysGroup);
  });
  return hysGroup;
}

function toggleHys(btn){
  hysOn=!hysOn;
  if(hysOn){ buildHysGroup().addTo(map); } else if(hysGroup){ map.removeLayer(hysGroup); }
  btn.classList.toggle('hys-active',hysOn);
}

// ── campus switch ──────────────────────────────────────────────────────────
function setCampus(campus){
  window.CAMPUS=campus;

  // update selector styles
  document.querySelectorAll('.campus-btn').forEach(function(b){
    b.classList.toggle('campus-active', b.dataset.campus===campus);
  });

  if(campus==='viikki'){
    map.setView(VIIKKI_LL, VIIKKI_ZOOM);
  } else {
    map.fitBounds(AALTO_BOUNDS);
    addAaltoTarget();
  }
}

// ── build viewControls UI ──────────────────────────────────────────────────
function buildUI(){
  if(typeof map==='undefined'||typeof L==='undefined') return false;
  var host=document.getElementById('viewControls');
  if(!host) return false;
  if(document.getElementById('campusSelector')) return true;

  // ── campus selector (top of panel) ──
  var sel=document.createElement('div');
  sel.id='campusSelector';
  sel.className='campus-selector';
  sel.innerHTML='<span class="campus-label">目标校区</span>'
    +'<button class="vc-btn campus-btn campus-active" data-campus="viikki">Viikki</button>'
    +'<button class="vc-btn campus-btn" data-campus="aalto">Aalto Otaniemi</button>';
  host.insertBefore(sel,host.firstChild);
  sel.querySelectorAll('.campus-btn').forEach(function(b){
    b.addEventListener('click',function(){ setCampus(b.dataset.campus); });
  });

  // ── HOAS button (remove old if present, add fresh) ──
  var old=document.getElementById('hoasToggleBtn');
  if(old) old.parentNode.removeChild(old);
  var hb=document.createElement('button');
  hb.id='hoasToggleBtn'; hb.className='vc-btn';
  hb.textContent='④ HOAS 房源';
  hb.addEventListener('click',function(){ toggleHoas(hb); });
  host.appendChild(hb);

  var conditions=[], hasUnknown=false;
  (HOAS_DATA.features||[]).forEach(function(f){ if(!(f.properties||{}).condition) hasUnknown=true; });
  (HOAS_DATA.features||[]).forEach(function(f){ var c=(f.properties||{}).condition; if(c&&conditions.indexOf(c)<0) conditions.push(c); });
  conditions.sort();
  if(conditions.length || hasUnknown){
    var filter=document.createElement('div');
    filter.id='hoasConditionFilter'; filter.className='hoas-condition-filter';
    [['all','全部'],].concat(conditions.map(function(c){return [c,c];})).concat(hasUnknown ? [['__unknown__','未标注']] : []).forEach(function(item){
      var b=document.createElement('button'); b.type='button'; b.dataset.condition=item[0]; b.textContent=item[1];
      b.addEventListener('click',function(){ setHoasCondition(item[0]); }); filter.appendChild(b);
    });
    host.appendChild(filter); syncConditionButtons();
  }

  // ── HYS button ──
  var old2=document.getElementById('hysToggleBtn');
  if(old2) old2.parentNode.removeChild(old2);
  var yb=document.createElement('button');
  yb.id='hysToggleBtn'; yb.className='vc-btn';
  yb.textContent='⑤ HYS 房源';
  yb.addEventListener('click',function(){ toggleHys(yb); });
  host.appendChild(yb);

  // ── Aalto threshold buttons (hidden until Aalto campus selected) ──
  var tc=document.createElement('div');
  tc.id='aaltoThresholdCtrl'; tc.className='threshold-ctrl';
  tc.style.display='flex';
  tc.innerHTML='<span class="campus-label">Aalto 通勤圈</span>';
  THRESHOLDS.forEach(function(m){
    var b=document.createElement('button');
    b.id='aaltoThr'+m; b.className='vc-btn thr-btn';
    b.textContent='≤'+m+'min';
    b.style.setProperty('--thr-color', COLORS[m]);
    b.addEventListener('click',function(){
      // clicking active top threshold collapses to previous; clicking any sets that threshold
      var next = (aaltoThreshold===m) ? (THRESHOLDS[THRESHOLDS.indexOf(m)-1]||0) : m;
      applyThreshold(next);
    });
    tc.appendChild(b);
  });
  host.appendChild(tc);

  // also remove any stale buttons from old injections
  ['aaltoViewBtn','aaltoListingsBtn','zoneToggleBtn'].forEach(function(id){
    // keep zoneToggleBtn (HSL zones), only remove Aalto-specific old ones
  });
  ['aaltoViewBtn','aaltoListingsBtn'].forEach(function(id){
    var el=document.getElementById(id);
    if(el) el.parentNode.removeChild(el);
  });

  return true;
}

function tryBuild(){ try{ return buildUI(); }catch(e){ return false; } }
if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',tryBuild);
else tryBuild();
[200,600,1500,3000].forEach(function(ms){ setTimeout(tryBuild,ms); });

})();
</script>'''

js = js.replace('__COMMUTE__', json.dumps(commute, ensure_ascii=False, separators=(',', ':')))
js = js.replace('__HOAS__',    json.dumps(hoas,    ensure_ascii=False, separators=(',', ':')))
js = js.replace('__HYS__',     json.dumps(hys,     ensure_ascii=False, separators=(',', ':')))

if '</body></html>' in text:
    text = text.replace('</body></html>', js + '\n</body></html>', 1)
elif '</body>' in text:
    text = text.replace('</body>', js + '\n</body>', 1)
else:
    text = text + '\n' + js

index.write_text(text, encoding='utf-8')
print('Done: campus-aware layers injected.')
print(f'  HOAS: {len(hoas.get("features",[]))} buildings ({sum(1 for f in hoas.get("features",[]) if f["properties"].get("aalto_otaniemi_40min"))} within 40min of Aalto)')
print(f'  HYS:  {len(hys.get("features",[]))} buildings')
print(f'  Aalto commute features: {len(commute.get("features",[]))}')
