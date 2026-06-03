"""ui.map — Обзор контура: граф ЖЦ + сводка за смену + живой поток (дизайн-handoff).

Порт прототипа Claude Design в серверный рендер. Граф: пайплайн-цепочка + ветвление
сервинг→эндпоинты→монитор; «живой поток» (бегущий пунктир + токены); сводка тяжести +
проблемные узлы; терминальный фид (findings + аудит). Контракт live-поллера сохранён:
узлы id=n-<id>, статус через CSS-var --c, поллер /api/map/status перекрашивает.
"""
from .layout import _e, _page
from .fragments import audit_fragment
from ..mapnodes import CONTROLS, PREVENTIVE, SHORT


_SC = {"clean": "var(--sa-ok)", "warn": "var(--sa-warn)", "alert": "var(--sa-alert)"}
_LVL = {"info": "var(--sa-text2)", "ok": "var(--sa-ok)", "warn": "var(--sa-warn)",
        "err": "var(--sa-alert)", "sec": "var(--sa-accent-ink)"}


def _ov_css():
    return (
        "<link href='https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap' rel=stylesheet>"
        "<style>"
        ".sa-ov{--sa-bg:#0b1220;--sa-panel:#111a2e;--sa-panel2:#0e1626;--sa-panel3:#15203a;"
        "--sa-line:#1f2a44;--sa-line2:#28344f;--sa-text:#cbd5e1;--sa-text2:#94a3b8;--sa-muted:#64748b;"
        "--sa-head:#f1f5f9;--sa-accent:#facc15;--sa-accent-ink:#facc15;--sa-ok:#10b981;--sa-warn:#f59e0b;"
        "--sa-alert:#ef4444;--sa-blue:#38bdf8;--sa-term-bg:#080c15;"
        "--sa-card-grad:linear-gradient(180deg,#15203a,#101a30);"
        "--sa-track-grad:radial-gradient(120% 150% at 0% 0%,#13213c 0%,#0d1526 58%);"
        "color:var(--sa-text);font-family:'Inter',ui-sans-serif,system-ui,sans-serif;}"
        ".sa-ov *{box-sizing:border-box;}"
        ".sa-mono{font-family:'JetBrains Mono',ui-monospace,Menlo,Consolas,monospace;font-variant-numeric:tabular-nums;}"
        ".sa-led{display:inline-block;border-radius:50%;background:var(--c,#475569);box-shadow:0 0 7px 0 var(--c);flex:none;}"
        "@keyframes saFlow{to{stroke-dashoffset:-24}}"
        "@keyframes saNodePulse{0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,.42)}50%{box-shadow:0 0 0 7px rgba(239,68,68,0)}}"
        "@keyframes saLed{0%,100%{box-shadow:0 0 6px 0 var(--c)}50%{box-shadow:0 0 14px 3px var(--c)}}"
        "@keyframes saPing{0%{box-shadow:0 0 0 0 rgba(16,185,129,.55)}70%{box-shadow:0 0 0 6px rgba(16,185,129,0)}100%{box-shadow:0 0 0 0 rgba(16,185,129,0)}}"
        # шапка
        ".sa-eye{display:flex;align-items:center;gap:8px;font-size:10.5px;letter-spacing:1.5px;text-transform:uppercase;color:var(--sa-text2);font-weight:600;}"
        ".sa-eye::before{content:'';width:14px;height:2px;background:var(--sa-accent);border-radius:2px;}"
        ".sa-live{display:inline-flex;align-items:center;gap:7px;font-size:11px;color:var(--sa-text2);border:1px solid var(--sa-line);border-radius:999px;padding:5px 11px;background:var(--sa-panel2);}"
        ".sa-live .d{width:7px;height:7px;border-radius:50%;background:var(--sa-ok);animation:saPing 1.9s infinite;}"
        # граф
        ".sa-graph{position:relative;border:1px solid var(--sa-line);border-radius:16px;background:var(--sa-track-grad);box-shadow:0 1px 2px rgba(0,0,0,.5);height:372px;overflow:hidden;}"
        ".sa-scaled-wrap{position:absolute;inset:0;}"
        ".sa-scaled{position:absolute;top:0;left:0;transform-origin:top left;}"
        ".sa-node{position:absolute;display:flex;flex-direction:column;justify-content:center;gap:3px;padding:0 10px;cursor:pointer;"
        "border:1px solid var(--sa-line);border-radius:10px;background:var(--sa-card-grad);transition:box-shadow .15s,border-color .15s,background .15s;}"
        ".sa-node:hover{border-color:var(--sa-accent);box-shadow:0 0 0 3px rgba(250,204,21,.18);background:var(--sa-panel3);}"
        ".sa-node.gate{border-radius:4px;border-left:3px solid var(--sa-accent);}"
        ".sa-node.alert{box-shadow:0 0 14px -2px var(--sa-alert);animation:saNodePulse 1.9s ease-in-out infinite;}"
        ".sa-node.alert:hover{animation:none;}"
        ".sa-nrow{display:flex;align-items:center;gap:6px;}"
        ".sa-nlabel{font-size:11.5px;font-weight:600;color:var(--sa-head);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}"
        ".sa-nmeta{font-size:8.5px;color:var(--sa-muted);}.sa-ngate{font-size:8px;font-weight:800;color:var(--sa-accent-ink);}"
        ".sa-nopen{font-size:9.5px;font-weight:700;margin-left:auto;}"
        ".sa-glabel{position:absolute;top:12px;left:16px;z-index:3;}"
        ".sa-ghint{position:absolute;top:11px;right:14px;z-index:3;font-size:10px;color:var(--sa-muted);}"
        # нижний ряд
        ".sa-bottom{display:grid;grid-template-columns:320px 1fr;gap:12px;height:300px;margin-top:12px;}"
        ".sa-sum{border:1px solid var(--sa-line);border-radius:14px;background:var(--sa-panel);padding:14px;display:flex;flex-direction:column;min-height:0;}"
        ".sa-sev{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-bottom:13px;}"
        ".sa-sevcell{display:flex;align-items:center;gap:8px;border:1px solid var(--sa-line);border-radius:9px;padding:8px 10px;background:var(--sa-panel2);}"
        ".sa-sevsq{width:8px;height:8px;border-radius:2px;flex:none;}"
        ".sa-sublbl{font-size:10px;letter-spacing:1.2px;text-transform:uppercase;color:var(--sa-muted);font-weight:600;margin-bottom:8px;}"
        ".sa-plist{overflow-y:auto;flex:1;min-height:0;display:flex;flex-direction:column;gap:5px;}"
        ".sa-prow{display:flex;align-items:center;gap:9px;border:1px solid var(--sa-line);border-radius:9px;padding:8px 10px;cursor:pointer;background:var(--sa-panel2);}"
        ".sa-prow:hover{border-color:var(--sa-accent);}"
        # терминал-фид
        ".sa-term{border:1px solid var(--sa-line);border-radius:12px;overflow:hidden;background:var(--sa-term-bg);display:flex;flex-direction:column;min-height:0;}"
        ".sa-term-h{display:flex;align-items:center;gap:8px;padding:7px 11px;border-bottom:1px solid var(--sa-line);background:rgba(255,255,255,.02);flex:none;}"
        ".sa-term-h i{width:8px;height:8px;border-radius:4px;display:inline-block;}"
        ".sa-term-b{flex:1;min-height:0;overflow-y:auto;padding:8px 11px;color:#e2e8f0;}"
        ".sa-tl{display:flex;gap:10px;padding:2px 0;font-size:12px;line-height:1.55;}"
        ".sa-tl .t{color:var(--sa-muted);flex:none;}.sa-tl .src{flex:none;width:104px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}"
        ".sa-scroll::-webkit-scrollbar{width:8px;height:8px}.sa-scroll::-webkit-scrollbar-thumb{background:var(--sa-line2);border-radius:8px}.sa-scroll::-webkit-scrollbar-track{background:transparent}"
        ".sa-chip{font-size:10.5px;color:var(--sa-text2);border:1px solid var(--sa-line);border-radius:6px;padding:2px 7px;}"
        "@media(prefers-reduced-motion:reduce){.sa-node.alert,.sa-led,.sa-live .d{animation:none!important}}"
        "</style>"
    )


def _ov_node(n, w, h, gate, endpoint):
    nid = _e(n["id"])
    cls = "sa-node" + (" gate" if gate else "") + (" alert" if n["status"] == "alert" else "")
    color = _SC.get(n["status"], "var(--sa-muted)")
    label = n["label"] if endpoint else n.get("short") or n["label"]
    left, top = n["x"] - w / 2, n["y"] - h / 2
    open_n = n.get("open") or 0
    badge = (f"<span class='sa-nopen sa-mono' style='color:{color}'>● {open_n}</span>" if open_n else "")
    if endpoint:
        foot = ""
        target = "serving"
    else:
        meta = ("<span class='sa-ngate sa-mono'>◇ GATE</span>" if gate
                else f"<span class='sa-nmeta sa-mono'>{n.get('ctrl', 0)} ctrl</span>")
        foot = f"<div class='sa-nrow'>{meta}{badge}</div>"
        target = nid
    return (
        f"<div id='n-{nid}' class='{cls}' data-node='{nid}' style='left:{left:.0f}px;top:{top:.0f}px;width:{w}px;height:{h}px;--c:{color}' "
        f"onclick='ovDrill(\"{_e(target)}\")' onmouseenter='ovHover(\"{nid}\")' onmouseleave='ovHover(null)'>"
        f"<div class='sa-nrow'><span class='sa-led' style='width:8px;height:8px'></span>"
        f"<span class='sa-nlabel{' sa-mono' if endpoint else ''}'>{_e(label)}</span></div>{foot}</div>"
    )


def map_page(pipeline, infra, endpoints=None, feed=None, sev_counts=None):
    endpoints = endpoints or []
    feed = feed or []
    sev_counts = sev_counts or {"critical": 0, "high": 0, "medium": 0, "low": 0}
    W, H, GY, EY = 1432, 372, 286, 116
    step = (W - 172) / 9
    main = []
    for i, p in enumerate(pipeline):
        main.append({**p, "x": 86 + i * step, "y": GY, "short": SHORT.get(p["id"], p["label"]),
                     "ctrl": len(CONTROLS.get(p["id"], [])), "prev": p["id"] in PREVENTIVE})
    by_id = {m["id"]: m for m in main}
    serving = by_id.get("serving", main[min(7, len(main) - 1)])
    monitor = by_id.get("monitor", main[min(8, len(main) - 1)])
    eps = [{**e, "x": serving["x"] - 70 + i * 110, "y": EY} for i, e in enumerate(endpoints[:4])]

    # рёбра: цепочка + ветвление + слияние
    edges = []
    for i in range(len(main) - 1):
        edges.append((main[i]["x"], main[i]["y"], main[i + 1]["x"], main[i + 1]["y"], main[i + 1]["status"]))
    for e in eps:
        edges.append((serving["x"], serving["y"], e["x"], e["y"], e.get("state", "clean")))
        edges.append((e["x"], e["y"], monitor["x"], monitor["y"], "clean"))

    def epath(ax, ay, bx, by):
        mx = (ax + bx) / 2
        return f"M {ax:.0f} {ay:.0f} C {mx:.0f} {ay:.0f}, {mx:.0f} {by:.0f}, {bx:.0f} {by:.0f}"

    edge_svg = ""
    for ax, ay, bx, by, st in edges:
        hot = st in ("alert", "warn")
        col = "var(--sa-alert)" if st == "alert" else "var(--sa-warn)" if st == "warn" else "var(--sa-line2)"
        d = epath(ax, ay, bx, by)
        edge_svg += (f"<path d='{d}' fill=none stroke='var(--sa-line)' stroke-width=2 marker-end='url(#ovarr)' opacity=.7/>"
                     f"<path d='{d}' fill=none stroke='{col}' stroke-width='{2.4 if hot else 1.8}' stroke-dasharray='5 7' "
                     f"style='animation:saFlow 1s linear infinite;opacity:{.95 if hot else .5}'/>")
    main_path = "M " + " L ".join(f"{m['x']:.0f} {m['y']}" for m in main)
    svg = (
        f"<svg width={W} height={H} viewBox='0 0 {W} {H}' style='position:absolute;top:0;left:0;overflow:visible'>"
        "<defs><marker id=ovarr markerWidth=7 markerHeight=7 refX=5.5 refY=3 orient=auto>"
        "<path d='M0 0 L6 3 L0 6 Z' fill='var(--sa-line2)'/></marker></defs>"
        f"{edge_svg}"
        f"<circle r=4.5 fill='var(--sa-blue)' opacity=.9><animateMotion dur=7s repeatCount=indefinite path='{main_path}'/></circle>"
        f"<circle r=3.5 fill='var(--sa-accent)' opacity=.85><animateMotion dur=7s begin=3.5s repeatCount=indefinite path='{main_path}'/></circle>"
        "</svg>"
    )
    nodes_html = "".join(_ov_node(m, 118, 52, m.get("gate"), False) for m in main)
    nodes_html += "".join(_ov_node({**e, "status": e.get("state", "clean")}, 102, 40, False, True) for e in eps)
    ep_caption = (f"<div class='sa-mono' style='position:absolute;left:{serving['x']-60:.0f}px;top:150px;font-size:9.5px;color:var(--sa-muted)'>live endpoints · RT-01/02/06</div>" if eps else "")

    graph = (
        "<div class='sa-graph'>"
        "<div class='sa-eye sa-glabel'>Граф контура · поток ЖЦ модели</div>"
        "<div class='sa-ghint sa-mono'>клик по узлу — детали · ховер — фильтр потока</div>"
        f"<div class='sa-scaled-wrap'><div class='sa-scaled' id='ov-scaled' style='width:{W}px;height:{H}px'>"
        f"{svg}{nodes_html}{ep_caption}</div></div></div>"
    )

    # сводка
    sev_meta = [("critical", "крит.", "var(--sa-alert)"), ("high", "высок.", "#fb923c"),
                ("medium", "сред.", "var(--sa-warn)"), ("low", "низк.", "var(--sa-muted)")]
    sev_html = "".join(
        f"<div class='sa-sevcell'><span class='sa-sevsq' style='background:{col};box-shadow:0 0 7px 0 {col}'></span>"
        f"<span class='sa-mono' style='font-size:17px;font-weight:700;color:var(--sa-head)'>{sev_counts.get(k,0)}</span>"
        f"<span style='font-size:10.5px;color:var(--sa-muted);margin-left:auto'>{ru}</span></div>"
        for k, ru, col in sev_meta)
    problems = sorted([n for n in (list(pipeline) + list(infra)) if (n.get("open") or 0) > 0],
                      key=lambda n: ((n.get("status") == "alert"), n.get("open") or 0), reverse=True)
    prob_html = "".join(
        f"<div class='sa-prow' onclick='ovDrill(\"{_e(n['id'])}\")'>"
        f"<span class='sa-led' style='width:8px;height:8px;--c:{_SC.get(n['status'],'var(--sa-muted)')}'></span>"
        f"<span style='font-size:12px;color:var(--sa-text);font-weight:500;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>{_e(SHORT.get(n['id'],n['label']))}</span>"
        f"<span class='sa-mono' style='font-size:10.5px;font-weight:700;color:{_SC.get(n['status'],'var(--sa-muted)')}'>● {n['open']}</span>"
        f"<span style='color:var(--sa-line2)'>›</span></div>"
        for n in problems) or "<div style='font-size:12px;color:var(--sa-muted);padding:6px 2px'>открытых сработок на узлах нет — контур спокоен</div>"
    summary = (
        "<div class='sa-sum'>"
        "<div class='sa-eye' style='margin-bottom:11px'>Сводка за смену</div>"
        f"<div class='sa-sev'>{sev_html}</div>"
        "<div class='sa-sublbl'>Узлы с сработками</div>"
        f"<div class='sa-plist sa-scroll'>{prob_html}</div></div>"
    )

    # терминал-фид (данные встроены, JS «протекает» и фильтрует по ховеру)
    import json
    feed_json = json.dumps(feed, ensure_ascii=False).replace("</", "<\\/")
    term = (
        "<div class='sa-term'><div class='sa-term-h'>"
        "<i style='background:#ef4444'></i><i style='background:#f59e0b'></i><i style='background:#10b981'></i>"
        "<span class='sa-mono' style='font-size:10.5px;color:var(--sa-text2)' id='ov-feed-title'>feed · all nodes</span></div>"
        "<div class='sa-term-b sa-scroll sa-mono' id='ov-feed'></div></div>"
    )

    body = (
        _ov_css() +
        "<div class='sa-ov'>"
        "<div style='display:flex;align-items:flex-end;justify-content:space-between;gap:1rem;flex-wrap:wrap;margin-bottom:12px'>"
        "<div><div class='sa-eye'>Sirius Argus · обзор контура</div>"
        "<div style='font-size:21px;font-weight:700;color:var(--sa-head);margin-top:3px'>Пайплайн ML-системы</div></div>"
        "<div class='sa-live'><span class='d'></span>LIVE · обновлено <span id='ov-upd'>—</span></div></div>"
        f"{graph}"
        f"<div class='sa-bottom'>{summary}{term}</div>"
        "<div class='sa-eye' style='margin:18px 0 10px'>Детали узла</div>"
        "<div id='map-drill' class='bg-white rounded-xl border border-slate-200 p-4 text-slate-400 text-sm'>"
        "выберите узел на графе — провалитесь в его сработки и аудит</div>"
        "</div>"
        f"<script>const OV_FEED={feed_json};</script>"
        "<script>" + _OV_JS + "</script>"
    )
    return _page("Sirius Argus — обзор контура", body, "map")


_OV_JS = r"""
(function(){
  var SC={clean:'var(--sa-ok)',warn:'var(--sa-warn)',alert:'var(--sa-alert)'};
  var LVL={info:'var(--sa-text2)',ok:'var(--sa-ok)',warn:'var(--sa-warn)',err:'var(--sa-alert)',sec:'var(--sa-accent-ink)'};
  // масштаб графа под ширину контейнера (как viewBox)
  function fit(){var w=document.querySelector('.sa-scaled-wrap'),s=document.getElementById('ov-scaled');
    if(!w||!s)return; s.style.transform='scale('+(w.clientWidth/1432)+')';}
  if(window.ResizeObserver){var ro=new ResizeObserver(fit);var wr=document.querySelector('.sa-scaled-wrap');if(wr)ro.observe(wr);}
  window.addEventListener('resize',fit); fit();
  // живой поток
  var hov=null, cursor=Math.min(16,OV_FEED.length);
  function esc(s){return String(s==null?'':s).replace(/[&<>]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});}
  function renderFeed(){
    var box=document.getElementById('ov-feed'); if(!box)return;
    var lines=OV_FEED.slice(0,cursor).filter(function(l){return !hov||l.node===hov||l.node==null;});
    box.innerHTML=lines.map(function(l){return "<div class='sa-tl'><span class='t'>"+esc(l.t)+"</span>"+
      "<span class='src' style='color:"+(LVL[l.lvl]||'var(--sa-text2)')+"'>"+esc(l.src)+"</span>"+
      "<span style='color:"+((l.lvl==='err'||l.lvl==='sec')?(LVL[l.lvl]):'#cbd5e1')+"'>"+esc(l.msg)+"</span></div>";}).join('')
      || "<div style='color:var(--sa-muted);font-size:12px'>// поток пуст</div>";
    box.scrollTop=box.scrollHeight;
    var tt=document.getElementById('ov-feed-title'); if(tt)tt.textContent=hov?('feed · filter='+hov):'feed · all nodes';
  }
  setInterval(function(){cursor=cursor>=OV_FEED.length?Math.min(12,OV_FEED.length):cursor+1;renderFeed();},1500);
  renderFeed();
  window.ovHover=function(id){hov=id;renderFeed();};
  // drill через HTMX/fetch (как было)
  window.ovDrill=function(id){
    var box=document.getElementById('map-drill');
    if(window.htmx){htmx.ajax('GET','/ui/map/node/'+id,'#map-drill');}
    else{fetch('/ui/map/node/'+id).then(function(r){return r.text();}).then(function(h){box.innerHTML=h;});}
    document.querySelectorAll('.sa-node').forEach(function(e){e.style.outline='';});
    var c=document.getElementById('n-'+id); if(c)c.style.outline='2px solid var(--sa-accent)';
    box.scrollIntoView({behavior:'smooth',block:'nearest'});
  };
  // live-поллер: перекраска узлов + KPI
  function poll(){
    fetch('/api/map/status').then(function(r){return r.json();}).then(function(s){
      var N=s.nodes||{};
      for(var k in N){var n=N[k],el=document.getElementById('n-'+k); if(!el)continue;
        var st=n.status||'clean'; el.style.setProperty('--c',SC[st]);
        el.classList.toggle('alert',st==='alert');
        var b=el.querySelector('.sa-nopen'); if(b){b.textContent=n.open?('● '+n.open):''; b.style.color=SC[st];}}
      var u=document.getElementById('ov-upd'); if(u)u.textContent=new Date().toLocaleTimeString('ru-RU');
    }).catch(function(){});
  }
  setInterval(poll,4000); poll();
})();
"""


def map_node_fragment(node_id, label, controls, findings, audit_rows):
    """Drill-панель узла: активные контроли + сработки (кликабельны → инцидент) + хвост аудита."""
    from .layout import _SEV, _STATUS
    ctl = ("".join(f"<span class='px-2 py-0.5 rounded text-[10px] bg-slate-100 text-slate-600'>{_e(c)}</span> "
                   for c in controls) or "<span class='text-xs text-slate-400'>—</span>")
    if findings:
        frows = "".join(
            f"<tr class='border-t border-slate-100 hover:bg-slate-50 cursor-pointer' onclick='drillIncident({f['id']})'>"
            f"<td class='px-3 py-1.5 text-slate-400 whitespace-nowrap'>{_e(f['ts'])}</td>"
            f"<td class='px-3 py-1.5'><span class='px-2 py-0.5 rounded text-xs {_SEV.get(f['severity'], 'bg-slate-100')}'>{_e(f['verdict'])}</span></td>"
            f"<td class='px-3 py-1.5 font-mono text-xs'>{_e(f['asset'])}</td>"
            f"<td class='px-3 py-1.5 text-slate-500'>{_e(f['detail'])}</td>"
            f"<td class='px-3 py-1.5'><span class='px-2 py-0.5 rounded text-xs {_STATUS.get(f['status'], 'bg-slate-100')}'>{_e(f['status'])}</span></td></tr>"
            for f in findings)
        ftable = ("<table class='w-full text-sm'><thead class='bg-slate-50 text-slate-500 text-xs uppercase'>"
                  "<tr><th class='px-3 py-2 text-left'>время</th><th class='px-3 py-2 text-left'>вердикт</th>"
                  "<th class='px-3 py-2 text-left'>актив</th><th class='px-3 py-2 text-left'>детали</th>"
                  f"<th class='px-3 py-2 text-left'>статус</th></tr></thead><tbody>{frows}</tbody></table>")
    else:
        ftable = "<div class='p-3 text-slate-400 text-sm'>сработок по узлу нет — контроль спокоен</div>"
    audit_html = audit_fragment(audit_rows) if audit_rows else "<div class='p-3 text-slate-400 text-sm'>событий нет</div>"
    drill_js = ("<script>function drillIncident(id){"
                "if(window.htmx){htmx.ajax('GET','/ui/map/incident/'+id,'#map-incident');}"
                "else{fetch('/ui/map/incident/'+id).then(r=>r.text()).then(h=>{document.getElementById('map-incident').innerHTML=h;});}"
                "document.getElementById('map-incident').scrollIntoView({behavior:'smooth',block:'nearest'});}</script>")
    return ("<div class='flex items-baseline justify-between mb-2'>"
            f"<h3 class='font-semibold'>{_e(label)}</h3>"
            "<span class='text-xs text-slate-400'>клик по строке — провалиться в инцидент</span></div>"
            f"<div class='mb-3 flex flex-wrap gap-1'>{ctl}</div>"
            f"<div class='rounded-lg border border-slate-200 overflow-hidden mb-4'>{ftable}</div>"
            "<h4 class='text-xs uppercase text-slate-400 mb-1'>Аудит (хвост)</h4>"
            f"<div class='rounded-lg border border-slate-200 overflow-hidden'>{audit_html}</div>"
            f"{drill_js}<div id='map-incident' class='mt-4'></div>")


def map_incident_fragment(finding, audit_rows):
    """Инцидент: одна сработка + окно аудит-таймлайна (проваливание второго уровня)."""
    from .layout import _SEV, _STATUS
    if not finding:
        return "<div class='p-3 text-slate-400 text-sm'>сработка не найдена</div>"
    f = finding
    head = (f"<div class='flex items-center gap-2 mb-2'>"
            f"<span class='px-2 py-0.5 rounded text-xs {_SEV.get(f['severity'], 'bg-slate-100')}'>{_e(f['severity'])}</span>"
            f"<b>{_e(f['verdict'])}</b>"
            f"<span class='text-slate-400 text-xs'>· {_e(f['tool'])} · {_e(f['ts'])}</span></div>")
    meta = (f"<div class='text-sm text-slate-600 mb-1'>Актив: <span class='font-mono text-xs'>{_e(f['asset'])}</span></div>"
            f"<div class='text-sm text-slate-600 mb-1'>Что произошло: {_e(f['detail'])}</div>"
            f"<div class='text-sm text-slate-600 mb-3'>Триаж: "
            f"<span class='px-2 py-0.5 rounded text-xs {_STATUS.get(f['status'], 'bg-slate-100')}'>{_e(f['status'])}</span></div>")
    tl = audit_fragment(audit_rows) if audit_rows else "<div class='p-3 text-slate-400 text-sm'>событий нет</div>"
    return ("<div class='rounded-xl border-2 border-slate-300 bg-slate-50 p-4'>"
            "<div class='flex items-baseline justify-between'><h3 class='font-semibold'>Инцидент</h3>"
            "<span class='text-xs text-slate-400'>сработка + аудит-таймлайн</span></div>"
            f"{head}{meta}"
            "<h4 class='text-xs uppercase text-slate-400 mb-1'>Таймлайн (аудит)</h4>"
            f"<div class='rounded-lg border border-slate-200 bg-white overflow-hidden'>{tl}</div></div>")
