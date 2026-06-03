"""ui.map — рендер (вынесено из ui.py)."""
from .layout import _CDN, _STYLE, _SEV, _STATUS, _CRIT, _STAGE, _e, _NAV, _page, _card
from .fragments import audit_fragment


def _map_node(n):
    cls = {"clean": "map-clean", "warn": "map-warn", "alert": "map-alert"}.get(n.get("status", "clean"), "map-clean")
    gate = " ◇" if n.get("gate") else ""
    badge = f"● {n['open']}" if n.get("open") else ""
    nid = _e(n["id"])
    return (f"<div id='n-{nid}' class='map-node {cls} rounded-lg border-2 px-3 py-2 text-center min-w-[104px]' "
            f"onclick='drill(\"{nid}\")'>"
            f"<div class='text-xs font-medium leading-tight'>{_e(n['label'])}{gate}</div>"
            f"<span class='badge block mt-1 text-[10px] font-bold text-red-600'>{_e(badge)}</span></div>")


def map_page(pipeline, infra):
    """Гибрид: пайплайн ЖЦ с гейтами + полоса инфра-узлов. Цвет — live-статус (поллер
    /api/map/status, перекраска по id без пересборки DOM). Клик → drill в инциденты."""
    style = ("<style>"
             ".map-node{transition:all .3s;cursor:pointer;border-color:#1f2a44;background:#111a2e;color:#cbd5e1}"
             ".map-clean{border-color:#10b981;background:rgba(16,185,129,.12)}"
             ".map-warn{border-color:#f59e0b;background:rgba(245,158,11,.12)}"
             ".map-alert{border-color:#ef4444;background:rgba(239,68,68,.14);animation:mapPulse 1.6s ease-in-out infinite}"
             "@keyframes mapPulse{0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,.45)}50%{box-shadow:0 0 0 7px rgba(239,68,68,0)}}"
             "@media(prefers-reduced-motion:reduce){.map-alert{animation:none}}"
             "</style>")
    sep = "<span class='self-center text-slate-300 px-0.5'>▸</span>"
    prow = sep.join(_map_node(n) for n in pipeline)
    irow = "".join(_map_node(n) for n in infra)
    script = (
        "<script>"
        "async function refreshMap(){try{"
        "const s=await fetch('/api/map/status').then(r=>r.json());"
        "for(const k in (s.nodes||{})){const n=s.nodes[k],el=document.getElementById('n-'+k);if(!el)continue;"
        "el.classList.remove('map-clean','map-warn','map-alert');el.classList.add('map-'+(n.status||'clean'));"
        "const b=el.querySelector('.badge');if(b)b.textContent=n.open?('\\u25cf '+n.open):'';}"
        "}catch(e){}}"
        "function drill(id){"
        "if(window.htmx){htmx.ajax('GET','/ui/map/node/'+id,'#map-drill');}"
        "else{fetch('/ui/map/node/'+id).then(r=>r.text()).then(h=>{document.getElementById('map-drill').innerHTML=h;});}"
        "document.querySelectorAll('.map-node').forEach(e=>e.classList.remove('ring-2','ring-slate-900'));"
        "const c=document.getElementById('n-'+id);if(c)c.classList.add('ring-2','ring-slate-900');"
        "document.getElementById('map-drill').scrollIntoView({behavior:'smooth',block:'nearest'});}"
        "setInterval(refreshMap,4000);document.addEventListener('DOMContentLoaded',refreshMap);"
        "</script>"
    )
    body = (
        style +
        "<h1 class='text-xl font-semibold'>Пайплайн — карта системы</h1>"
        "<p class='text-sm text-slate-500'>Узлы пайплайна и инфраструктуры; цвет — live-статус: "
        "<span class='text-emerald-600'>зелёный</span> чисто/armed, <span class='text-amber-600'>янтарь</span> есть open, "
        "<span class='text-red-600'>красный</span> critical/блокировка. Клик по узлу → его сработки и аудит; "
        "клик по сработке → инцидент. Превентивные контроли (HITL, output-reduction, сегментация) зелёные, пока работают молча.</p>"
        "<section><h2 class='font-semibold mb-2 text-xs uppercase text-slate-400'>Пайплайн ЖЦ</h2>"
        f"<div class='flex flex-wrap items-stretch gap-1 bg-white rounded-xl border border-slate-200 p-4'>{prow}</div></section>"
        "<section><h2 class='font-semibold mb-2 text-xs uppercase text-slate-400'>Инфра-узлы</h2>"
        f"<div class='flex flex-wrap gap-2 bg-white rounded-xl border border-slate-200 p-4'>{irow}</div></section>"
        "<section><h2 class='font-semibold mb-2'>Детали узла</h2>"
        "<div id='map-drill' class='bg-white rounded-xl shadow-sm border border-slate-200 p-4 text-slate-400 text-sm'>"
        "выбери узел на схеме, чтобы провалиться в его сработки и аудит</div></section>" +
        script
    )
    return _page("Sirius Argus — пайплайн", body, "map")


def map_node_fragment(node_id, label, controls, findings, audit_rows):
    """Drill-панель узла: активные контроли + сработки (кликабельны → инцидент) + хвост аудита."""
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
