"""ui.map — рендер карты пайплайна (вынесено из ui.py)."""
from .layout import _CDN, _STYLE, _SEV, _STATUS, _CRIT, _STAGE, _e, _NAV, _page, _card
from .fragments import audit_fragment
from ..mapnodes import CONTROLS, PREVENTIVE


_STATE_TXT = {"clean": "OPERATIONAL", "warn": "ВНИМАНИЕ", "alert": "ТРЕВОГА"}
_SCLS = {"clean": "map-clean", "warn": "map-warn", "alert": "map-alert"}

# Фазовые группы конвейера (узлы внутри — в порядке PIPELINE).
_PHASES = (
    ("Сборка", ("intake", "gate-data", "train", "package", "gate-artifact")),
    ("Промоушен", ("validate", "gate-ci")),
    ("Эксплуатация", ("serving", "monitor", "decommission")),
)


def _node_tile(n, idx=None, gate=False, infra=False):
    """Узел-плитка карты. Контракт live-поллера: id=n-<id>, класс map-node + map-<status>,
    дочерний .badge (open-счётчик), onclick=drill. Статус задаёт CSS-переменную --s (цвет
    LED/границы/свечения) — поллер просто перевешивает map-<status>, и плитка перекрашивается."""
    status = n.get("status", "clean")
    classes = "map-node " + _SCLS.get(status, "map-clean")
    if gate:
        classes += " nt-gate"
    if n["id"] in PREVENTIVE:
        classes += " nt-prev"
    nid = _e(n["id"])
    nctrl = len(CONTROLS.get(n["id"], []))
    open_n = n.get("open") or 0
    badge = f"● {open_n}" if open_n else ""
    if gate:
        top_left = "<span class='nt-tag'>◇ GATE</span>"
    elif infra:
        top_left = "<span class='nt-kind'>сервис</span>"
    else:
        top_left = f"<span class='nt-idx'>{idx:02d}</span>" if idx is not None else "<span class='nt-idx'>··</span>"
    foot = (
        "<div class='nt-foot'>"
        f"<span class='badge'>{_e(badge)}</span>"
        + (f"<span class='nt-ctrl'>{nctrl} контр.</span>" if nctrl else "")
        + ("<span class='nt-armed'>armed</span>" if n["id"] in PREVENTIVE else "")
        + "</div>"
    )
    return (
        f"<div id='n-{nid}' class='{classes}' onclick='drill(\"{nid}\")'>"
        f"<div class='nt-top'>{top_left}<span class='led'></span></div>"
        f"<div class='nt-label'>{_e(n['label'])}</div>"
        f"{foot}</div>"
    )


def _map_css():
    return (
        "<style>"
        # статус → CSS-переменная цвета (перевешивается поллером)
        ".map-clean{--s:#10b981}.map-warn{--s:#f59e0b}.map-alert{--s:#ef4444}"
        # шапка экрана
        ".map-head{display:flex;align-items:flex-end;justify-content:space-between;gap:1rem;flex-wrap:wrap;margin-bottom:16px}"
        ".map-eyebrow{font-size:11px;letter-spacing:2px;text-transform:uppercase;color:var(--text2);font-weight:600}"
        ".map-h1{font-size:22px;font-weight:700;color:var(--head);margin-top:3px}"
        ".map-sub{font-size:12.5px;color:var(--text2);max-width:680px;margin-top:5px;line-height:1.55}"
        ".live{display:inline-flex;align-items:center;gap:7px;font-size:11px;color:var(--text2);border:1px solid var(--line);"
        "border-radius:999px;padding:6px 12px;background:#0c1424;white-space:nowrap}"
        ".live .dot{width:7px;height:7px;border-radius:50%;background:#34d399;animation:lvp 1.9s infinite}"
        "@keyframes lvp{0%{box-shadow:0 0 0 0 rgba(52,211,153,.55)}70%{box-shadow:0 0 0 6px rgba(52,211,153,0)}100%{box-shadow:0 0 0 0 rgba(52,211,153,0)}}"
        # KPI-полоса
        ".kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:12px;margin-bottom:22px}"
        ".kpi{position:relative;border:1px solid var(--line);border-radius:14px;padding:14px 16px;"
        "background:linear-gradient(180deg,#121d33,#0e1626);overflow:hidden}"
        ".kpi::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,var(--accent),transparent)}"
        ".kpi .l{font-size:10px;letter-spacing:1.4px;text-transform:uppercase;color:var(--text2);font-weight:600}"
        ".kpi .v{font-size:28px;font-weight:700;color:var(--head);line-height:1.05;margin-top:7px;font-variant-numeric:tabular-nums;display:flex;align-items:center;gap:9px}"
        ".kpi .s{font-size:11px;color:var(--muted);margin-top:4px}"
        ".kpi.state{border-color:var(--s,#1f2a44)}"
        ".kpi.state::before{background:linear-gradient(90deg,var(--s,var(--accent)),transparent)}"
        ".kpi.state .v{font-size:19px;letter-spacing:.6px}"
        # LED
        ".led{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--s,#475569);box-shadow:0 0 7px 0 var(--s);flex:none}"
        ".map-alert .led{animation:ledp 1.4s infinite}"
        "@keyframes ledp{0%,100%{box-shadow:0 0 6px 0 var(--s)}50%{box-shadow:0 0 13px 2px var(--s)}}"
        # секционный заголовок
        ".sec-eyebrow{display:flex;align-items:center;gap:8px;font-size:11px;letter-spacing:1.6px;text-transform:uppercase;"
        "color:var(--text2);font-weight:600;margin:22px 0 11px}"
        ".sec-eyebrow::before{content:'';width:14px;height:2px;background:var(--accent);border-radius:2px}"
        # панель-трек конвейера
        ".track-panel{position:relative;border:1px solid var(--line);border-radius:18px;padding:18px 18px 16px;"
        "background:radial-gradient(120% 150% at 0% 0%,#13213c 0%,#0d1526 58%);box-shadow:0 1px 2px rgba(0,0,0,.5),inset 0 0 0 1px rgba(255,255,255,.02)}"
        ".track{display:flex;align-items:stretch;gap:22px;overflow-x:auto;padding:4px 2px 14px}"
        # фазовые группы конвейера
        ".phase{display:flex;flex-direction:column;gap:9px;flex:none}"
        ".phase-label{font-size:9.5px;letter-spacing:1.4px;text-transform:uppercase;color:var(--text2);"
        "font-weight:700;padding:0 2px 6px;border-bottom:1px dashed var(--line)}"
        ".phase-row{display:flex;align-items:stretch}"
        ".phase+.phase{position:relative}"
        ".phase+.phase::before{content:'›';position:absolute;left:-16px;top:50%;color:var(--accent);font-size:18px;line-height:0}"
        ".track::-webkit-scrollbar{height:8px}.track::-webkit-scrollbar-thumb{background:#1f2a44;border-radius:8px}.track::-webkit-scrollbar-track{background:transparent}"
        # узел-плитка
        ".map-node{flex:none;min-width:130px;max-width:152px;border:1px solid var(--line);border-radius:13px;padding:11px 12px 10px;"
        "background:linear-gradient(180deg,#15203a,#101a30);cursor:pointer;position:relative;border-top:2px solid var(--s,#334155);"
        "transition:transform .18s,border-color .18s,box-shadow .18s}"
        ".map-node:hover{transform:translateY(-2px);border-color:var(--s,#334155);box-shadow:0 8px 20px -10px var(--s)}"
        ".map-node.sel{outline:2px solid var(--accent);outline-offset:2px}"
        ".map-node.map-alert{animation:mapPulse 1.9s ease-in-out infinite}"
        "@keyframes mapPulse{0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,.42)}50%{box-shadow:0 0 0 6px rgba(239,68,68,0)}}"
        ".nt-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;min-height:18px}"
        ".nt-idx{font-size:11px;font-weight:700;color:var(--text2);font-variant-numeric:tabular-nums;letter-spacing:1px}"
        ".nt-kind{font-size:9px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;color:var(--muted)}"
        ".nt-tag{font-size:9.5px;font-weight:700;letter-spacing:.8px;color:#0b1220;background:var(--accent);border-radius:5px;padding:2px 6px}"
        ".nt-label{font-size:12.5px;font-weight:600;color:var(--head);line-height:1.2;min-height:31px;display:flex;align-items:center}"
        ".nt-foot{display:flex;align-items:center;gap:6px;margin-top:9px;flex-wrap:wrap;min-height:18px}"
        ".badge{font-size:11px;font-weight:700;color:var(--s,#94a3b8);font-variant-numeric:tabular-nums}"
        ".nt-ctrl{font-size:9.5px;color:var(--text2);border:1px solid var(--line);border-radius:5px;padding:1px 5px}"
        ".nt-armed{font-size:9px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;color:#34d399;"
        "border:1px solid rgba(52,211,153,.32);background:rgba(16,185,129,.12);border-radius:5px;padding:1px 5px;display:none}"
        ".map-node.nt-prev.map-clean .nt-armed{display:inline-block}"
        # коннектор между стадиями
        ".conn{flex:none;width:30px;align-self:center;height:2px;position:relative;"
        "background:linear-gradient(90deg,#243250,#1a2540)}"
        ".conn::after{content:'›';position:absolute;right:-2px;top:-12px;color:#46557a;font-size:17px;line-height:1}"
        # грид инфраструктуры
        ".infra-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(152px,1fr));gap:11px}"
        ".infra-grid .map-node{max-width:none;min-width:0}"
        ".infra-grid .nt-label{min-height:0}"
        # легенда
        ".legend{display:flex;flex-wrap:wrap;gap:8px 16px;margin-top:14px;padding-top:13px;border-top:1px solid var(--line);font-size:11px;color:var(--text2)}"
        ".legend span{display:inline-flex;align-items:center;gap:6px}"
        ".lg-led{width:8px;height:8px;border-radius:50%;display:inline-block}"
        "@media(prefers-reduced-motion:reduce){.map-node.map-alert,.led,.live .dot{animation:none!important}}"
        "</style>"
    )


def map_page(pipeline, infra):
    """Командная панель контура: KPI-полоса состояния + конвейер ЖЦ как связанный трек с
    гейтами + грид инфра-узлов + легенда. Цвет — live-статус (поллер /api/map/status, без
    пересборки DOM). Клик по узлу → drill в его сработки и аудит; клик по сработке → инцидент."""
    alln = list(pipeline) + list(infra)
    open_total = sum((n.get("open") or 0) for n in alln)
    alerts = sum(1 for n in alln if n.get("status") == "alert")
    warns = sum(1 for n in alln if n.get("status") == "warn")
    gates = [n for n in pipeline if n.get("gate")]
    gates_armed = sum(1 for n in gates if n.get("status") == "clean")
    ctrl_total = sum(len(CONTROLS.get(n["id"], [])) for n in alln)
    state = "alert" if alerts else ("warn" if warns else "clean")

    header = (
        "<div class='map-head'><div>"
        "<div class='map-eyebrow'>Sirius Argus · карта контура</div>"
        "<div class='map-h1'>Пайплайн ML-системы</div>"
        "<div class='map-sub'>Сквозной контур: жизненный цикл модели с fail-closed гейтами плюс инфраструктура. "
        "Цвет узла — live-статус; клик — провал в сработки узла, далее в инцидент и аудит-таймлайн.</div>"
        "</div><div class='live'><span class='dot'></span>LIVE · обновлено <span id='map-updated'>—</span></div></div>"
    )

    kpis = (
        "<div class='kpis'>"
        f"<div id='kpi-state-tile' class='kpi state map-{state}'><div class='l'>Состояние контура</div>"
        f"<div class='v'><span class='led'></span><span id='kpi-state'>{_STATE_TXT[state]}</span></div>"
        f"<div class='s'>{len(alln)} узлов под наблюдением</div></div>"
        f"<div class='kpi'><div class='l'>Открытых сработок</div><div class='v' id='kpi-open'>{open_total}</div>"
        "<div class='s'>в активной триаж-очереди</div></div>"
        f"<div class='kpi'><div class='l'>Гейты armed</div><div class='v' id='kpi-gates'>{gates_armed}/{len(gates)}</div>"
        "<div class='s'>fail-closed контроль</div></div>"
        f"<div class='kpi'><div class='l'>Узлов под тревогой</div><div class='v' id='kpi-alerts'>{alerts}</div>"
        "<div class='s'>high / critical</div></div>"
        f"<div class='kpi'><div class='l'>Контролей в контуре</div><div class='v'>{ctrl_total}</div>"
        "<div class='s'>средств защиты активно</div></div>"
        "</div>"
    )

    conn = "<span class='conn'></span>"
    idx_of = {n["id"]: i + 1 for i, n in enumerate(pipeline)}
    by_id = {n["id"]: n for n in pipeline}
    phase_blocks = []
    for ph_name, ids in _PHASES:
        ph_nodes = [by_id[i] for i in ids if i in by_id]
        inner = conn.join(_node_tile(n, idx=idx_of[n["id"]], gate=n.get("gate")) for n in ph_nodes)
        phase_blocks.append(
            f"<div class='phase'><div class='phase-label'>{_e(ph_name)}</div>"
            f"<div class='phase-row'>{inner}</div></div>")
    track = "".join(phase_blocks)  # фазы разделяются gap'ом трека, узлы внутри — коннекторами
    infra_html = "".join(_node_tile(n, infra=True) for n in infra)

    legend = (
        "<div class='legend'>"
        "<span><i class='lg-led' style='background:#10b981'></i>armed / чисто</span>"
        "<span><i class='lg-led' style='background:#f59e0b'></i>есть открытые</span>"
        "<span><i class='lg-led' style='background:#ef4444'></i>тревога · high/critical</span>"
        "<span><b style='color:var(--accent)'>◇ GATE</b> — fail-closed гейт</span>"
        "<span><b style='color:#34d399'>armed</b> — превентивный контроль работает молча</span>"
        "<span><b style='color:var(--text)'>● N</b> — открытых сработок</span>"
        "</div>"
    )

    script = (
        "<script>"
        "function setTxt(id,v){var e=document.getElementById(id);if(e)e.textContent=v;}"
        "async function refreshMap(){try{"
        "var s=await fetch('/api/map/status').then(function(r){return r.json();});"
        "var N=s.nodes||{},open=0,alerts=0,warns=0,gA=0,gT=0;"
        "for(var k in N){var n=N[k],el=document.getElementById('n-'+k);open+=(n.open||0);"
        "if(n.status==='alert')alerts++;else if(n.status==='warn')warns++;"
        "if(el){el.classList.remove('map-clean','map-warn','map-alert');el.classList.add('map-'+(n.status||'clean'));"
        "var b=el.querySelector('.badge');if(b)b.textContent=n.open?('\\u25cf '+n.open):'';"
        "if(el.classList.contains('nt-gate')){gT++;if((n.status||'clean')==='clean')gA++;}}}"
        "setTxt('kpi-open',open);setTxt('kpi-alerts',alerts);if(gT)setTxt('kpi-gates',gA+'/'+gT);"
        "var st=alerts?'alert':(warns?'warn':'clean');"
        "setTxt('kpi-state',st==='alert'?'ТРЕВОГА':(st==='warn'?'ВНИМАНИЕ':'OPERATIONAL'));"
        "var tl=document.getElementById('kpi-state-tile');"
        "if(tl){tl.classList.remove('map-clean','map-warn','map-alert');tl.classList.add('map-'+st);}"
        "var u=document.getElementById('map-updated');if(u)u.textContent=new Date().toLocaleTimeString('ru-RU');"
        "}catch(e){}}"
        "function drill(id){"
        "if(window.htmx){htmx.ajax('GET','/ui/map/node/'+id,'#map-drill');}"
        "else{fetch('/ui/map/node/'+id).then(function(r){return r.text();}).then(function(h){document.getElementById('map-drill').innerHTML=h;});}"
        "document.querySelectorAll('.map-node').forEach(function(e){e.classList.remove('sel');});"
        "var c=document.getElementById('n-'+id);if(c)c.classList.add('sel');"
        "document.getElementById('map-drill').scrollIntoView({behavior:'smooth',block:'nearest'});}"
        "setInterval(refreshMap,4000);document.addEventListener('DOMContentLoaded',refreshMap);refreshMap();"
        "</script>"
    )

    body = (
        _map_css() + header + kpis +
        "<div class='sec-eyebrow'>Конвейер жизненного цикла</div>"
        f"<div class='track-panel'><div class='track'>{track}</div>{legend}</div>"
        "<div class='sec-eyebrow'>Инфраструктура контура</div>"
        f"<div class='infra-grid'>{infra_html}</div>"
        "<div class='sec-eyebrow'>Детали узла</div>"
        "<div id='map-drill' class='bg-white rounded-xl border border-slate-200 p-4 text-slate-400 text-sm'>"
        "выберите узел на схеме — провалитесь в его сработки и аудит</div>"
        + script
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
