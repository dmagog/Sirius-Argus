"""ui.map — приложение «Обзор контура» (порт дизайн-handoff Claude Design).

Full-bleed оболочка: node-centric рейл (Конвейер ЖЦ + Инфраструктура) + топбар (KPI)
+ контент. Два экрана: Обзор (граф ЖЦ с ветвлением + сводка + живой поток) и Инспектор
узла (шапка + сработки + лог; очередь прогонов — stage B). Данные реальные. Контракт
live-поллера сохранён: узлы id=n-<id>, статус через CSS-var --c, /api/map/status.
"""
import json
from .fragments import audit_fragment  # noqa: F401  (используется в map_node_fragment)
from .layout import _NAV
from ..mapnodes import CONTROLS, PREVENTIVE, SHORT
import html as _html


def _e(s):
    return _html.escape(str(s if s is not None else ""))


_SC = {"clean": "var(--sa-ok)", "warn": "var(--sa-warn)", "alert": "var(--sa-alert)"}
_LVL = {"info": "var(--sa-text2)", "ok": "var(--sa-ok)", "warn": "var(--sa-warn)",
        "err": "var(--sa-alert)", "sec": "var(--sa-accent-ink)"}
_SEVC = {"critical": "var(--sa-alert)", "high": "#fb923c", "medium": "var(--sa-warn)",
         "low": "var(--sa-muted)", "info": "var(--sa-muted)"}
# Bootstrap-иконки разделов верхнего уровня (по ключу _NAV).
_NAV_ICON = {"map": "bi-diagram-3", "dashboard": "bi-speedometer2", "registry": "bi-box-seam",
             "findings": "bi-exclamation-triangle", "coverage": "bi-shield-check",
             "serving": "bi-hdd-network", "services": "bi-hdd-stack", "roles": "bi-people"}


def _sa_css():
    return (
        "<style>"
        ":root{--sa-bg:#0b1220;--sa-panel:#111a2e;--sa-panel2:#0e1626;--sa-panel3:#15203a;"
        "--sa-line:#1f2a44;--sa-line2:#28344f;--sa-text:#cbd5e1;--sa-text2:#94a3b8;--sa-muted:#64748b;"
        "--sa-head:#f1f5f9;--sa-accent:#facc15;--sa-accent-ink:#facc15;--sa-ok:#10b981;--sa-warn:#f59e0b;"
        "--sa-alert:#ef4444;--sa-blue:#38bdf8;--sa-term-bg:#080c15;"
        "--sa-card-grad:linear-gradient(180deg,#15203a,#101a30);"
        "--sa-track-grad:radial-gradient(120% 150% at 0% 0%,#13213c 0%,#0d1526 58%);}"
        # светлая тема — переключается data-sa-theme='light' на <html> (терминал остаётся тёмным)
        "[data-sa-theme='light']{--sa-bg:#eef1f5;--sa-panel:#ffffff;--sa-panel2:#f6f8fb;--sa-panel3:#ffffff;"
        "--sa-line:#e2e8f0;--sa-line2:#dbe3ec;--sa-text:#334155;--sa-text2:#64748b;--sa-muted:#94a3b8;"
        "--sa-head:#0f172a;--sa-accent:#eab308;--sa-accent-ink:#a16207;--sa-ok:#059669;--sa-warn:#d97706;"
        "--sa-alert:#dc2626;--sa-blue:#0284c7;--sa-term-bg:#0f172a;"
        "--sa-card-grad:linear-gradient(180deg,#ffffff,#f7f9fc);"
        "--sa-track-grad:radial-gradient(120% 150% at 0% 0%,#ffffff 0%,#eef2f7 70%);}"
        ".sa-themebtn{display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;flex:none;"
        "border:1px solid var(--sa-line);border-radius:999px;background:var(--sa-panel);color:var(--sa-text2);cursor:pointer;font-size:14px;}"
        ".sa-themebtn:hover{border-color:var(--sa-accent);color:var(--sa-accent-ink);}"
        ".sa-accent-pick{display:inline-flex;align-items:center;gap:5px;}"
        ".sa-accent-pick button{width:15px;height:15px;border-radius:999px;border:2px solid transparent;background:var(--sw);cursor:pointer;padding:0;box-shadow:0 0 0 1px var(--sa-line);}"
        ".sa-accent-pick button[aria-current='true']{border-color:var(--sa-head);}"
        "*{box-sizing:border-box;}html,body{margin:0;height:100%;}"
        "body{background:var(--sa-bg);color:var(--sa-text);font-family:'Inter',ui-sans-serif,system-ui,sans-serif;-webkit-font-smoothing:antialiased;}"
        ".sa-mono{font-family:'JetBrains Mono',ui-monospace,Menlo,Consolas,monospace;font-variant-numeric:tabular-nums;}"
        ".sa-led{display:inline-block;border-radius:50%;background:var(--c,#475569);box-shadow:0 0 7px 0 var(--c);flex:none;}"
        "@keyframes saFlow{to{stroke-dashoffset:-24}}"
        "@keyframes saNodePulse{0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,.42)}50%{box-shadow:0 0 0 7px rgba(239,68,68,0)}}"
        "@keyframes saPing{0%{box-shadow:0 0 0 0 rgba(16,185,129,.55)}70%{box-shadow:0 0 0 6px rgba(16,185,129,0)}100%{box-shadow:0 0 0 0 rgba(16,185,129,0)}}"
        "@keyframes saScreen{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}"
        ".sa-scroll::-webkit-scrollbar{width:8px;height:8px}.sa-scroll::-webkit-scrollbar-thumb{background:var(--sa-line2);border-radius:8px}.sa-scroll::-webkit-scrollbar-track{background:transparent}"
        ".sa-scroll{scrollbar-width:thin;scrollbar-color:var(--sa-line2) transparent;}"
        # ── каркас ──
        ".sa-app{display:flex;height:100vh;overflow:hidden;}"
        ".sa-rail{width:250px;flex:none;border-right:1px solid var(--sa-line);background:var(--sa-panel2);display:flex;flex-direction:column;min-height:0;}"
        ".sa-brand{display:flex;align-items:center;gap:10px;padding:16px;border-bottom:1px solid var(--sa-line);text-decoration:none;}"
        ".sa-brand .star{width:34px;height:34px;border-radius:999px;flex:none;display:flex;align-items:center;justify-content:center;"
        "background:radial-gradient(circle at 50% 45%,rgba(250,204,21,.32) 0%,rgba(250,204,21,.10) 60%,rgba(250,204,21,0) 100%);box-shadow:0 0 14px rgba(250,204,21,.25);}"
        ".sa-brand .t1{display:block;font-weight:700;font-size:15px;color:var(--sa-head);letter-spacing:.3px;line-height:1.1;}"
        ".sa-brand .t2{display:block;font-size:8.5px;letter-spacing:1.6px;text-transform:uppercase;color:var(--sa-text2);font-weight:500;margin-top:3px;}"
        ".sa-railitem{display:flex;align-items:center;gap:11px;padding:10px 11px;border-radius:10px;cursor:pointer;text-decoration:none;}"
        ".sa-railitem .ic{width:30px;height:30px;flex:none;border-radius:8px;display:flex;align-items:center;justify-content:center;background:var(--sa-panel);border:1px solid var(--sa-line);color:var(--sa-text2);font-size:14px;}"
        ".sa-railitem .l1{display:block;font-size:13px;font-weight:600;color:var(--sa-text);}"
        ".sa-railitem .l2{display:block;font-size:9.5px;color:var(--sa-muted);margin-top:2px;}"
        ".sa-railitem:hover{background:var(--sa-panel);}"
        ".sa-railitem.on{background:var(--sa-panel3);box-shadow:inset 3px 0 0 var(--sa-accent),0 0 0 1px var(--sa-line);}"
        ".sa-railitem.on .ic{background:rgba(250,204,21,.14);color:var(--sa-accent-ink);}.sa-railitem.on .l1{color:var(--sa-head);}"
        ".sa-filter{position:relative;}.sa-filter span{position:absolute;left:9px;top:50%;transform:translateY(-50%);color:var(--sa-muted);font-size:11px;}"
        ".sa-filter input{width:100%;padding:7px 9px 7px 26px;font-size:11.5px;color:var(--sa-text);background:var(--sa-panel);border:1px solid var(--sa-line);border-radius:8px;outline:none;}"
        ".sa-filter input:focus{border-color:var(--sa-accent);}"
        ".sa-raillbl{font-size:9.5px;letter-spacing:1.4px;text-transform:uppercase;color:var(--sa-muted);font-weight:600;padding:14px 9px 8px;}"
        ".bi{line-height:1;vertical-align:-.05em;}"
        ".sa-sec{display:flex;align-items:center;gap:10px;padding:7px 10px;border-radius:8px;cursor:pointer;text-decoration:none;color:var(--sa-text2);font-size:12.5px;}"
        ".sa-sec i{font-size:14px;width:18px;text-align:center;color:var(--sa-muted);flex:none;}"
        ".sa-sec:hover{background:var(--sa-panel);color:var(--sa-text);}"
        ".sa-sec.on{background:var(--sa-panel3);box-shadow:inset 3px 0 0 var(--sa-accent);color:var(--sa-head);font-weight:600;}"
        ".sa-sec.on i{color:var(--sa-accent-ink);}"
        ".sa-stage{display:flex;align-items:center;gap:9px;padding:8px 9px;border-radius:8px;cursor:pointer;margin-bottom:2px;text-decoration:none;}"
        ".sa-stage:hover{background:var(--sa-panel);}.sa-stage.on{background:var(--sa-panel3);box-shadow:inset 3px 0 0 var(--sa-accent);}"
        ".sa-stage .ix{font-size:9.5px;width:15px;text-align:center;flex:none;}"
        ".sa-stage .nm{font-size:12px;color:var(--sa-text);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}"
        ".sa-stage.on .nm{color:var(--sa-head);font-weight:600;}"
        ".sa-stage .cnt{font-size:9.5px;font-weight:700;border-radius:999px;padding:1px 7px;flex:none;}.sa-stage .ok{font-size:9.5px;color:var(--sa-ok);opacity:.7;flex:none;}"
        ".sa-infra{display:flex;align-items:center;gap:9px;padding:6px 9px;border-radius:8px;cursor:pointer;text-decoration:none;}"
        ".sa-infra:hover{background:var(--sa-panel);}.sa-infra.on{background:var(--sa-panel3);box-shadow:inset 3px 0 0 var(--sa-accent);}"
        ".sa-infra .nm{font-size:11.5px;color:var(--sa-text2);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}.sa-infra.on .nm{color:var(--sa-head);}"
        ".sa-railfoot{padding:10px 14px;border-top:1px solid var(--sa-line);display:flex;justify-content:space-between;font-size:9.5px;color:var(--sa-muted);}"
        # ── правая колонка ──
        ".sa-main{flex:1;min-width:0;display:flex;flex-direction:column;overflow:hidden;}"
        ".sa-top{flex:none;height:60px;padding:0 22px;border-bottom:1px solid var(--sa-line);background:var(--sa-panel2);display:flex;align-items:center;justify-content:space-between;gap:1rem;}"
        ".sa-bc{display:flex;align-items:center;gap:10px;min-width:0;}"
        ".sa-bc .h{font-size:15px;font-weight:700;color:var(--sa-head);}.sa-bc .s{font-size:10.5px;color:var(--sa-muted);}"
        ".sa-back{display:flex;align-items:center;gap:6px;font-size:11.5px;color:var(--sa-text2);background:var(--sa-panel);border:1px solid var(--sa-line);border-radius:8px;padding:6px 11px;cursor:pointer;text-decoration:none;}"
        ".sa-back:hover{border-color:var(--sa-accent);color:var(--sa-head);}"
        ".sa-kpis{display:flex;align-items:center;gap:18px;flex:none;}"
        ".sa-kpi{display:flex;flex-direction:column;align-items:flex-end;line-height:1;}"
        ".sa-kpi .v{font-size:17px;font-weight:700;}.sa-kpi .k{font-size:8.5px;letter-spacing:1px;text-transform:uppercase;color:var(--sa-muted);margin-top:3px;}"
        ".sa-live{display:inline-flex;align-items:center;gap:7px;font-size:11px;color:var(--sa-text2);border:1px solid var(--sa-line);border-radius:999px;padding:5px 11px;background:var(--sa-panel);}"
        ".sa-live .d{width:7px;height:7px;border-radius:50%;background:var(--sa-ok);animation:saPing 1.9s infinite;}"
        ".sa-content{flex:1;min-height:0;overflow:auto;animation:saScreen .26s ease;}"
        ".sa-eye{display:flex;align-items:center;gap:8px;font-size:10.5px;letter-spacing:1.5px;text-transform:uppercase;color:var(--sa-text2);font-weight:600;}"
        ".sa-eye::before{content:'';width:14px;height:2px;background:var(--sa-accent);border-radius:2px;}"
        # ── граф ──
        ".sa-graph{position:relative;border:1px solid var(--sa-line);border-radius:16px;background:var(--sa-track-grad);box-shadow:0 1px 2px rgba(0,0,0,.5);height:392px;overflow:hidden;}"
        ".sa-scaled-wrap{position:absolute;inset:0;}.sa-scaled{position:absolute;top:0;left:0;transform-origin:top left;}"
        ".sa-node{position:absolute;display:flex;flex-direction:column;justify-content:center;gap:3px;padding:0 10px;cursor:pointer;text-decoration:none;"
        "border:1px solid var(--sa-line);border-radius:10px;background:var(--sa-card-grad);transition:box-shadow .15s,border-color .15s,background .15s;}"
        ".sa-node:hover{border-color:var(--sa-accent);box-shadow:0 0 0 3px rgba(250,204,21,.18);background:var(--sa-panel3);}"
        ".sa-node.gate{border-radius:4px;border-left:3px solid var(--sa-accent);}"
        ".sa-node.alert{box-shadow:0 0 14px -2px var(--sa-alert);animation:saNodePulse 1.9s ease-in-out infinite;}.sa-node.alert:hover{animation:none;}"
        ".sa-nrow{display:flex;align-items:center;gap:6px;}"
        ".sa-nlabel{font-size:11.5px;font-weight:600;color:var(--sa-head);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}"
        ".sa-nmeta{font-size:8.5px;color:var(--sa-muted);}.sa-ngate{font-size:8px;font-weight:800;color:var(--sa-accent-ink);}.sa-nopen{font-size:9.5px;font-weight:700;margin-left:auto;}"
        ".sa-glabel{position:absolute;top:12px;left:16px;z-index:3;}.sa-ghint{position:absolute;top:11px;right:14px;z-index:3;font-size:10px;color:var(--sa-muted);}"
        # ── нижний ряд ──
        ".sa-bottom{display:grid;grid-template-columns:340px 1fr;gap:14px;height:300px;margin-top:14px;}"
        ".sa-sum{border:1px solid var(--sa-line);border-radius:14px;background:var(--sa-panel);padding:14px;display:flex;flex-direction:column;min-height:0;}"
        ".sa-sev{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-bottom:13px;}"
        ".sa-sevcell{display:flex;align-items:center;gap:8px;border:1px solid var(--sa-line);border-radius:9px;padding:8px 10px;background:var(--sa-panel2);}"
        ".sa-sublbl{font-size:10px;letter-spacing:1.2px;text-transform:uppercase;color:var(--sa-muted);font-weight:600;margin-bottom:8px;}"
        ".sa-plist{overflow-y:auto;flex:1;min-height:0;display:flex;flex-direction:column;gap:5px;}"
        ".sa-prow{display:flex;align-items:center;gap:9px;border:1px solid var(--sa-line);border-radius:9px;padding:8px 10px;cursor:pointer;background:var(--sa-panel2);text-decoration:none;}"
        ".sa-prow:hover{border-color:var(--sa-accent);}"
        # ── терминал ──
        ".sa-term{border:1px solid var(--sa-line);border-radius:12px;overflow:hidden;background:var(--sa-term-bg);display:flex;flex-direction:column;min-height:0;}"
        ".sa-term-h{display:flex;align-items:center;gap:8px;padding:7px 11px;border-bottom:1px solid var(--sa-line);background:rgba(255,255,255,.02);flex:none;}"
        ".sa-term-h i{width:8px;height:8px;border-radius:4px;display:inline-block;}"
        ".sa-term-b{flex:1;min-height:0;overflow-y:auto;padding:8px 11px;color:#e2e8f0;}"
        ".sa-tl{display:flex;gap:10px;padding:2px 0;font-size:12px;line-height:1.55;}"
        ".sa-tl .t{color:var(--sa-muted);flex:none;}.sa-tl .src{flex:none;width:104px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}"
        # ── инспектор-lite ──
        ".sa-insp{padding:18px 22px;}.sa-chip{font-size:10.5px;color:var(--sa-text2);border:1px solid var(--sa-line);border-radius:6px;padding:3px 8px;}"
        ".sa-fcard{border:1px solid var(--sa-line);border-radius:10px;padding:11px 13px;background:var(--sa-panel);margin-bottom:8px;}"
        ".sa-runcard{display:block;border:1px solid var(--sa-line);border-radius:11px;padding:11px 13px;margin-bottom:8px;text-decoration:none;transition:border-color .15s,box-shadow .15s;}"
        ".sa-runcard:hover{border-color:var(--sa-accent);}"
        ".sa-lin{display:flex;justify-content:space-between;gap:10px;padding:7px 11px;}.sa-lin+.sa-lin{border-top:1px solid var(--sa-line);}"
        ".sa-badge{font-size:10px;font-weight:700;border-radius:5px;padding:2px 6px;}"
        # ── hero-сплэш при входе (один раз за сессию; фон = --sa-bg, тема применена до отрисовки) ──
        ".sa-splash{position:fixed;inset:0;z-index:9999;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;background:var(--sa-bg);transition:opacity .4s ease;}"
        ".sa-splash.out{opacity:0;pointer-events:none;}"
        ".sa-splash .logo{width:96px;height:96px;border-radius:999px;display:flex;align-items:center;justify-content:center;"
        "background:radial-gradient(circle at 50% 45%,rgba(250,204,21,.34) 0%,rgba(250,204,21,.10) 60%,rgba(250,204,21,0) 100%);box-shadow:0 0 46px rgba(250,204,21,.28);animation:saSplashIn .5s ease;}"
        ".sa-splash .logo img{width:72px;height:72px;border-radius:999px;}"
        ".sa-splash .t1{font-size:21px;font-weight:700;color:var(--sa-head);letter-spacing:.4px;}"
        ".sa-splash .t2{font-size:9.5px;letter-spacing:2.4px;text-transform:uppercase;color:var(--sa-text2);font-weight:500;margin-top:5px;}"
        ".sa-splash .bar{width:182px;height:3px;border-radius:3px;background:var(--sa-line2);overflow:hidden;margin-top:8px;}"
        ".sa-splash .bar i{display:block;height:100%;width:0;border-radius:3px;background:linear-gradient(90deg,var(--sa-accent),var(--sa-accent-ink));}"
        ".sa-splash.go .bar i{animation:saSplashBar .82s ease forwards;}"
        "@keyframes saSplashIn{from{opacity:0;transform:scale(.92)}to{opacity:1;transform:none}}"
        "@keyframes saSplashBar{from{width:0}to{width:100%}}"
        "@media(prefers-reduced-motion:reduce){.sa-node.alert,.sa-led,.sa-live .d,.sa-content,.sa-splash .logo,.sa-splash.go .bar i{animation:none!important}.sa-splash .bar i{width:100%}}"
        "</style>"
    )


def _shell(active, pipeline, infra, breadcrumb, content, body_js="", title="Sirius Argus — обзор контура"):
    open_total = sum((n.get("open") or 0) for n in (list(pipeline) + list(infra)))
    gates = [n for n in pipeline if n.get("gate")]
    gates_ok = sum(1 for n in gates if n.get("status") != "alert")
    nnodes = len(pipeline) + len(infra)

    def stage_row(n, idx):
        on = " on" if active == n["id"] else ""
        st = n.get("status", "clean")
        col = _SC.get(st, "var(--sa-muted)")
        ix = "<i class='bi bi-diamond-fill'></i>" if n.get("gate") else f"{idx+1:02d}"
        ixcol = "var(--sa-accent-ink)" if n.get("gate") else "var(--sa-muted)"
        open_n = n.get("open") or 0
        if open_n:
            bg = "rgba(239,68,68,.15)" if st == "alert" else "rgba(245,158,11,.15)" if st == "warn" else "transparent"
            br = "rgba(239,68,68,.4)" if st == "alert" else "rgba(245,158,11,.4)" if st == "warn" else "transparent"
            cnt = f"<span class='cnt sa-mono' style='color:{col};background:{bg};border:1px solid {br}'>{open_n}</span>"
        else:
            cnt = "<span class='ok'><i class='bi bi-check2'></i></span>"
        return (f"<a class='sa-stage{on}' data-f='{_e((SHORT.get(n['id'],n['label'])+' '+n['label']).lower())}' href='/map/node/{_e(n['id'])}'>"
                f"<span class='sa-led' style='width:8px;height:8px;--c:{col}'></span>"
                f"<span class='ix sa-mono' style='color:{ixcol}'>{ix}</span>"
                f"<span class='nm'>{_e(SHORT.get(n['id'], n['label']))}</span>{cnt}</a>")

    def infra_row(n):
        on = " on" if active == n["id"] else ""
        col = _SC.get(n.get("status", "clean"), "var(--sa-muted)")
        open_n = n.get("open") or 0
        cnt = (f"<span class='sa-mono' style='font-size:9.5px;font-weight:700;color:{col}'>{open_n}</span>" if open_n else "")
        return (f"<a class='sa-infra{on}' data-f='{_e(n['label'].lower())}' href='/map/node/{_e(n['id'])}'>"
                f"<span class='sa-led' style='width:7px;height:7px;--c:{col}'></span>"
                f"<span class='nm'>{_e(n['label'])}</span>{cnt}</a>")

    sec_rows = "".join(
        f"<a class='sa-sec{(' on' if k=='map' else '')}' href='{h}'>"
        f"<i class='bi {_NAV_ICON.get(k, 'bi-dot')}'></i><span>{_e(l)}</span></a>"
        for h, l, k in _NAV)
    rail = (
        "<nav class='sa-rail'>"
        "<a class='sa-brand' href='/map' title='Sirius Argus'>"
        "<span class='star'><img src='/static/avatar.png' alt='' style='width:26px;height:26px;border-radius:999px'></span>"
        "<span><span class='t1'>Sirius Argus</span><span class='t2'>MLSecOps Platform</span></span></a>"
        f"<div style='padding:10px 12px 6px'><div class='sa-raillbl' style='padding:2px 9px 6px'>Разделы</div>{sec_rows}</div>"
        "<div style='padding:6px 12px;border-top:1px solid var(--sa-line)'>"
        f"<a class='sa-railitem{(' on' if active=='overview' else '')}' href='/map'>"
        "<span class='ic'><i class='bi bi-bullseye'></i></span><span style='min-width:0'><span class='l1'>Обзор контура</span><span class='l2'>граф ЖЦ · живой поток</span></span></a></div>"
        "<div style='padding:2px 14px 8px'><div class='sa-filter'><span><i class='bi bi-search'></i></span>"
        "<input class='sa-mono' id='sa-railfilter' placeholder='Фильтр узлов…' spellcheck=false oninput='saFilter(this.value)'></div></div>"
        "<div class='sa-scroll' style='flex:1;overflow-y:auto;padding:0 12px 10px;min-height:0'>"
        "<div class='sa-raillbl' style='padding-top:4px'>Конвейер ЖЦ</div>"
        + "".join(stage_row(n, i) for i, n in enumerate(pipeline))
        + "<div class='sa-raillbl'>Инфраструктура</div>"
        + "".join(infra_row(n) for n in infra)
        + "</div>"
        f"<div class='sa-railfoot'><span class='sa-mono'>argus · prod</span><span class='sa-mono'>{nnodes} узлов</span></div></nav>"
    )

    # hero-сплэш — только на стартовом экране (обзор); JS гасит его один раз за сессию
    splash = (
        "<div class='sa-splash' id='sa-splash'>"
        "<span class='logo'><img src='/static/avatar.png' alt='Sirius Argus'></span>"
        "<div style='text-align:center'><div class='t1'>Sirius Argus</div><div class='t2'>MLSecOps Platform</div></div>"
        "<div class='bar'><i></i></div></div>"
    ) if active == "overview" else ""

    gates_col = "var(--sa-alert)" if gates_ok < len(gates) else "var(--sa-ok)"
    topbar = (
        "<header class='sa-top'>"
        f"<div class='sa-bc'>{breadcrumb}</div>"
        "<div class='sa-kpis'>"
        f"<div class='sa-kpi'><span class='v sa-mono' style='color:var(--sa-head)'>{nnodes}</span><span class='k'>узлов</span></div>"
        f"<div class='sa-kpi'><span class='v sa-mono' style='color:var(--sa-warn)'>{open_total}</span><span class='k'>сработок</span></div>"
        f"<div class='sa-kpi'><span class='v sa-mono' style='color:{gates_col}'>{gates_ok}/{len(gates)}</span><span class='k'>гейтов</span></div>"
        "<span class='sa-accent-pick' title='Акцент'>"
        "<button data-a='' style='--sw:#facc15' onclick=\"saAccent('')\" title='Золото'></button>"
        "<button data-a='#fb923c' style='--sw:#fb923c' onclick=\"saAccent('#fb923c')\" title='Оранжевый'></button>"
        "<button data-a='#38bdf8' style='--sw:#38bdf8' onclick=\"saAccent('#38bdf8')\" title='Голубой'></button></span>"
        "<button class='sa-themebtn' onclick='saTheme()' title='Светлая / тёмная тема'><i id='sa-theme-ic' class='bi bi-moon-stars'></i></button>"
        "<span class='sa-live'><span class='d'></span>LIVE · <span id='sa-upd'>—</span></span></div></header>"
    )
    return (
        "<!doctype html><html lang=ru><head><meta charset=utf-8>"
        "<script>try{var _t=localStorage.getItem('sa-theme');if(_t)document.documentElement.setAttribute('data-sa-theme',_t);"
        "var _a=localStorage.getItem('sa-accent');if(_a){document.documentElement.style.setProperty('--sa-accent',_a);document.documentElement.style.setProperty('--sa-accent-ink',_a);}}catch(e){}</script>"
        "<meta name=viewport content='width=device-width, initial-scale=1'>"
        f"<title>{_e(title)}</title><link rel=icon type=image/png href='/static/avatar.png'>"
        "<link rel=preconnect href='https://fonts.googleapis.com'><link rel=preconnect href='https://fonts.gstatic.com' crossorigin>"
        "<link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap' rel=stylesheet>"
        "<link href='https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css' rel=stylesheet>"
        '<script src="https://unpkg.com/htmx.org@2.0.3"></script>'
        f"{_sa_css()}</head><body>{splash}"
        f"<div class='sa-app'>{rail}<div class='sa-main'>{topbar}"
        f"<div class='sa-content sa-scroll'>{content}</div></div></div>"
        f"<script>{_SHELL_JS}{body_js}</script></body></html>"
    )


_SHELL_JS = r"""
function saFilter(q){q=(q||'').toLowerCase();
  document.querySelectorAll('.sa-stage,.sa-infra').forEach(function(el){
    el.style.display=(!q||(el.getAttribute('data-f')||'').indexOf(q)>=0)?'':'none';});}
function saTheme(){var c=document.documentElement.getAttribute('data-sa-theme')||'dark';var n=c==='light'?'dark':'light';
  document.documentElement.setAttribute('data-sa-theme',n);try{localStorage.setItem('sa-theme',n);}catch(e){}saThemeIcon();}
function saThemeIcon(){var t=document.documentElement.getAttribute('data-sa-theme')||'dark';var i=document.getElementById('sa-theme-ic');
  if(i)i.className='bi '+(t==='light'?'bi-sun':'bi-moon-stars');}
function saAccent(a){var d=document.documentElement;
  if(a){d.style.setProperty('--sa-accent',a);d.style.setProperty('--sa-accent-ink',a);}
  else{d.style.removeProperty('--sa-accent');d.style.removeProperty('--sa-accent-ink');}
  try{a?localStorage.setItem('sa-accent',a):localStorage.removeItem('sa-accent');}catch(e){}saAccentMark();}
function saAccentMark(){var cur='';try{cur=localStorage.getItem('sa-accent')||'';}catch(e){}
  document.querySelectorAll('.sa-accent-pick [data-a],.sb-accent-pick [data-a]').forEach(function(b){
    b.setAttribute('aria-current',(b.getAttribute('data-a')||'')===cur?'true':'false');});}
(function(){saThemeIcon();saAccentMark();function tick(){var u=document.getElementById('sa-upd');if(u)u.textContent=new Date().toLocaleTimeString('ru-RU');}
 setInterval(tick,4000);tick();})();
// hero-сплэш: показываем один раз за сессию, гасим по таймеру (декоративный прогресс),
// уважаем prefers-reduced-motion; не блокирует контент (оверлей поверх готовой страницы).
(function(){var el=document.getElementById('sa-splash');if(!el)return;
 var seen;try{seen=sessionStorage.getItem('sa-splash-seen');}catch(e){}
 if(seen){if(el.parentNode)el.parentNode.removeChild(el);return;}
 try{sessionStorage.setItem('sa-splash-seen','1');}catch(e){}
 function done(){el.classList.add('out');setTimeout(function(){if(el.parentNode)el.parentNode.removeChild(el);},420);}
 var reduce=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
 if(reduce){setTimeout(done,260);return;}
 el.classList.add('go');setTimeout(done,1050);})();
"""


def _ov_node(n, w, h, gate, endpoint):
    nid = _e(n["id"])
    cls = "sa-node" + (" gate" if gate else "") + (" alert" if n.get("status") == "alert" else "")
    color = _SC.get(n.get("status"), "var(--sa-muted)")
    label = n["label"] if endpoint else n.get("short") or n["label"]
    left, top = n["x"] - w / 2, n["y"] - h / 2
    open_n = n.get("open") or 0
    badge = (f"<span class='sa-nopen sa-mono' style='color:{color}'>● {open_n}</span>" if open_n else "")
    if endpoint:
        foot, target = "", "serving"
    else:
        meta = ("<span class='sa-ngate sa-mono'>◇ GATE</span>" if gate
                else f"<span class='sa-nmeta sa-mono'>{n.get('ctrl', 0)} ctrl</span>")
        foot, target = f"<div class='sa-nrow'>{meta}{badge}</div>", nid
    return (
        f"<a id='n-{nid}' class='{cls}' href='/map/node/{_e(target)}' "
        f"style='left:{left:.0f}px;top:{top:.0f}px;width:{w}px;height:{h}px;--c:{color}' "
        f"onmouseenter='ovHover(\"{nid}\")' onmouseleave='ovHover(null)'>"
        f"<div class='sa-nrow'><span class='sa-led' style='width:8px;height:8px'></span>"
        f"<span class='sa-nlabel{' sa-mono' if endpoint else ''}'>{_e(label)}</span></div>{foot}</a>"
    )


# Легенда графа: явно разводим «здоровье узла» (его открытые сработки) и «поток ЖЦ».
# Снимает путаницу «почему нижестоящий узел зелёный, если на гейте было плохо»: цвет узла —
# про его собственные findings, а не про прохождение потока. Прогон по потоку — в инспекторе.
_OV_LEGEND = (
    "<div style='display:flex;align-items:center;gap:8px 18px;flex-wrap:wrap;margin:12px 2px 0;font-size:10.5px;color:var(--sa-muted)'>"
    "<span style='display:inline-flex;align-items:center;gap:6px'>"
    "<span class='sa-led' style='width:8px;height:8px;--c:var(--sa-alert)'></span>"
    "цвет узла — <b style='color:var(--sa-text2);font-weight:600'>здоровье узла</b> (его открытые сработки)</span>"
    "<span style='display:inline-flex;align-items:center;gap:6px'>"
    "<span style='width:18px;height:2px;background:#3a4d70;border-radius:2px;flex:none'></span>"
    "линия и частицы — <b style='color:var(--sa-text2);font-weight:600'>поток ЖЦ</b></span>"
    "<span style='flex:1;min-width:240px'>здоровье узла независимо от потока: зелёный узел ниже по конвейеру "
    "не значит, что прогон прошёл гейты чисто — прохождение конкретного прогона смотрите в инспекторе узла.</span>"
    "</div>"
)


def map_page(pipeline, infra, endpoints=None, feed=None, sev_counts=None):
    endpoints = endpoints or []
    feed = feed or []
    sev_counts = sev_counts or {"critical": 0, "high": 0, "medium": 0, "low": 0}
    W, H, GY, EY = 1432, 392, 300, 132
    step = (W - 172) / 9
    main = []
    for i, p in enumerate(pipeline):
        main.append({**p, "x": 86 + i * step, "y": GY, "short": SHORT.get(p["id"], p["label"]),
                     "ctrl": len(CONTROLS.get(p["id"], [])), "prev": p["id"] in PREVENTIVE})
    by_id = {m["id"]: m for m in main}
    serving = by_id.get("serving", main[min(7, len(main) - 1)])
    monitor = by_id.get("monitor", main[min(8, len(main) - 1)])
    eps = [{**e, "x": serving["x"] - 70 + i * 110, "y": EY} for i, e in enumerate(endpoints[:4])]

    edges = []
    for i in range(len(main) - 1):
        edges.append((main[i]["x"], main[i]["y"], main[i + 1]["x"], main[i + 1]["y"], main[i + 1]["status"]))
    for e in eps:
        edges.append((serving["x"], serving["y"], e["x"], e["y"], e.get("state", "clean")))
        edges.append((e["x"], e["y"], monitor["x"], monitor["y"], "clean"))

    def epath(ax, ay, bx, by):
        mx = (ax + bx) / 2
        return f"M {ax:.0f} {ay:.0f} C {mx:.0f} {ay:.0f}, {mx:.0f} {by:.0f}, {bx:.0f} {by:.0f}"

    # SVG-цвета — ХЕКСОМ (var(--sa-*) в атрибутах stroke/fill не резолвится).
    # Всё хорошо → сплошная непрерывная линия; warn/alert → тусклая база + бегущий пунктир.
    edge_svg = ""
    for ax, ay, bx, by, st in edges:
        d = epath(ax, ay, bx, by)
        if st in ("alert", "warn"):
            col = "#ef4444" if st == "alert" else "#f59e0b"
            edge_svg += (f"<path d='{d}' fill=none stroke='#28344f' stroke-width='2' marker-end='url(#ovarr)' opacity='.7'/>"
                         f"<path d='{d}' fill=none stroke='{col}' stroke-width='2.6' stroke-dasharray='5 7' opacity='.95'>"
                         "<animate attributeName='stroke-dashoffset' from='0' to='-24' dur='1s' repeatCount='indefinite'/></path>")
        else:
            edge_svg += f"<path d='{d}' fill=none stroke='#3a4d70' stroke-width='2' marker-end='url(#ovarr)' opacity='.9'/>"
    main_path = "M " + " L ".join(f"{m['x']:.0f} {m['y']}" for m in main)
    svg = (
        f"<svg width={W} height={H} viewBox='0 0 {W} {H}' style='position:absolute;top:0;left:0;overflow:visible'>"
        "<defs><marker id=ovarr markerWidth=7 markerHeight=7 refX=5.5 refY=3 orient=auto>"
        "<path d='M0 0 L6 3 L0 6 Z' fill='#46557a'/></marker></defs>"
        f"{edge_svg}"
        f"<circle r=4.5 fill='#38bdf8' opacity=.9><animateMotion dur=7s repeatCount=indefinite path='{main_path}'/></circle>"
        f"<circle r=3.5 fill='#facc15' opacity=.85><animateMotion dur=7s begin=3.5s repeatCount=indefinite path='{main_path}'/></circle>"
        "</svg>"
    )
    nodes_html = "".join(_ov_node(m, 122, 54, m.get("gate"), False) for m in main)
    nodes_html += "".join(_ov_node({**e, "status": e.get("state", "clean")}, 104, 40, False, True) for e in eps)
    ep_caption = (f"<div class='sa-mono' style='position:absolute;left:{serving['x']-60:.0f}px;top:166px;font-size:9.5px;color:var(--sa-muted)'>live endpoints · RT-01/02/06</div>" if eps else "")
    graph = (
        "<div class='sa-graph'>"
        "<div class='sa-eye sa-glabel'>Граф контура · поток ЖЦ модели</div>"
        "<div class='sa-ghint sa-mono'>клик по узлу — инспектор · ховер — фильтр потока</div>"
        f"<div class='sa-scaled-wrap'><div class='sa-scaled' id='ov-scaled' style='width:{W}px;height:{H}px'>{svg}{nodes_html}{ep_caption}</div></div></div>"
    )

    sev_meta = [("critical", "крит.", "var(--sa-alert)"), ("high", "высок.", "#fb923c"),
                ("medium", "сред.", "var(--sa-warn)"), ("low", "низк.", "var(--sa-muted)")]
    sev_html = "".join(
        f"<div class='sa-sevcell'><span style='width:8px;height:8px;border-radius:2px;flex:none;background:{col};box-shadow:0 0 7px 0 {col}'></span>"
        f"<span class='sa-mono' style='font-size:17px;font-weight:700;color:var(--sa-head)'>{sev_counts.get(k,0)}</span>"
        f"<span style='font-size:10.5px;color:var(--sa-muted);margin-left:auto'>{ru}</span></div>" for k, ru, col in sev_meta)
    problems = sorted([n for n in (list(pipeline) + list(infra)) if (n.get("open") or 0) > 0],
                      key=lambda n: ((n.get("status") == "alert"), n.get("open") or 0), reverse=True)
    prob_html = "".join(
        f"<a class='sa-prow' href='/map/node/{_e(n['id'])}'>"
        f"<span class='sa-led' style='width:8px;height:8px;--c:{_SC.get(n['status'],'var(--sa-muted)')}'></span>"
        f"<span style='font-size:12px;color:var(--sa-text);font-weight:500;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>{_e(SHORT.get(n['id'],n['label']))}</span>"
        f"<span class='sa-mono' style='font-size:10.5px;font-weight:700;color:{_SC.get(n['status'],'var(--sa-muted)')}'>● {n['open']}</span>"
        f"<span style='color:var(--sa-line2)'>›</span></a>" for n in problems) or "<div style='font-size:12px;color:var(--sa-muted);padding:6px 2px'>открытых сработок на узлах нет — контур спокоен</div>"
    summary = ("<div class='sa-sum'><div class='sa-eye' style='margin-bottom:11px'>Сводка за смену</div>"
               f"<div class='sa-sev'>{sev_html}</div><div class='sa-sublbl'>Узлы с сработками</div>"
               f"<div class='sa-plist sa-scroll'>{prob_html}</div></div>")
    term = ("<div class='sa-term'><div class='sa-term-h'>"
            "<i style='background:#ef4444'></i><i style='background:#f59e0b'></i><i style='background:#10b981'></i>"
            "<span class='sa-mono' style='font-size:10.5px;color:var(--sa-text2)' id='ov-feed-title'>feed · all nodes</span></div>"
            "<div class='sa-term-b sa-scroll sa-mono' id='ov-feed'></div></div>")
    feed_json = json.dumps(feed, ensure_ascii=False).replace("</", "<\\/")
    content = (
        "<div style='padding:16px 20px 20px'>"
        f"{graph}{_OV_LEGEND}<div class='sa-bottom'>{summary}{term}</div></div>"
        f"<script>const OV_FEED={feed_json};</script><script>{_OV_JS}</script>"
    )
    breadcrumb = "<div><div class='h'>Обзор контура</div><div class='s'>граф жизненного цикла модели · поток событий в реальном времени</div></div>"
    return _shell("overview", pipeline, infra, breadcrumb, content)


_OV_JS = r"""
(function(){
  var SC={clean:'var(--sa-ok)',warn:'var(--sa-warn)',alert:'var(--sa-alert)'};
  var LVL={info:'var(--sa-text2)',ok:'var(--sa-ok)',warn:'var(--sa-warn)',err:'var(--sa-alert)',sec:'var(--sa-accent-ink)'};
  // масштаб слоя по ширине + высота бокса следует за масштабом (иначе на не-1432 ширинах
  // контент короче фикс-бокса → пустота снизу; на широких — обрезался). Идемпотентно.
  function fit(){var wrap=document.querySelector('.sa-scaled-wrap'),s=document.getElementById('ov-scaled'),g=document.querySelector('.sa-graph');
    if(!wrap||!s||!wrap.clientWidth)return; var sc=wrap.clientWidth/1432; s.style.transform='scale('+sc+')';
    if(g){var hpx=Math.round(392*sc)+'px'; if(g.style.height!==hpx)g.style.height=hpx;}}
  if(window.ResizeObserver){var wr=document.querySelector('.sa-scaled-wrap');if(wr)new ResizeObserver(fit).observe(wr);}
  window.addEventListener('resize',fit); setTimeout(fit,0); fit();
  var hov=null, cursor=Math.min(16,OV_FEED.length);
  function esc(s){return String(s==null?'':s).replace(/[&<>]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});}
  function renderFeed(){var box=document.getElementById('ov-feed'); if(!box)return;
    var lines=OV_FEED.slice(0,cursor).filter(function(l){return !hov||l.node===hov||l.node==null;});
    box.innerHTML=lines.map(function(l){return "<div class='sa-tl'><span class='t'>"+esc(l.t)+"</span>"+
      "<span class='src' style='color:"+(LVL[l.lvl]||'var(--sa-text2)')+"'>"+esc(l.src)+"</span>"+
      "<span style='color:"+((l.lvl==='err'||l.lvl==='sec')?(LVL[l.lvl]):'#cbd5e1')+"'>"+esc(l.msg)+"</span></div>";}).join('')
      || "<div style='color:var(--sa-muted);font-size:12px'>// поток пуст</div>";
    box.scrollTop=box.scrollHeight;
    var tt=document.getElementById('ov-feed-title'); if(tt)tt.textContent=hov?('feed · filter='+hov):'feed · all nodes';}
  setInterval(function(){cursor=cursor>=OV_FEED.length?Math.min(12,OV_FEED.length):cursor+1;renderFeed();},1500);
  renderFeed();
  window.ovHover=function(id){hov=id;renderFeed();};
  function poll(){fetch('/api/map/status').then(function(r){return r.json();}).then(function(s){var N=s.nodes||{};
    for(var k in N){var n=N[k],el=document.getElementById('n-'+k); if(!el)continue; var st=n.status||'clean';
      el.style.setProperty('--c',SC[st]); el.classList.toggle('alert',st==='alert');
      var b=el.querySelector('.sa-nopen'); if(b){b.textContent=n.open?('● '+n.open):''; b.style.color=SC[st];}}
    }).catch(function(){});}
  setInterval(poll,4000); poll();
})();
"""


_RUNSTATE = {"blocked": ("var(--sa-alert)", "BLOCKED"), "failed": ("var(--sa-alert)", "FAILED"),
             "running": ("var(--sa-blue)", "RUNNING"), "hitl": ("var(--sa-warn)", "HITL"),
             "hold": ("var(--sa-warn)", "HOLD"), "passed": ("var(--sa-ok)", "PASSED"),
             "rejected": ("var(--sa-alert)", "REJECTED"), "retired": ("var(--sa-muted)", "RETIRED")}
_CRITB = {"regulatory": "var(--sa-alert)", "financial": "#fb923c", "internal": "var(--sa-muted)"}


def _rs_badge(state):
    c, t = _RUNSTATE.get(state, _RUNSTATE["passed"])
    return f"<span class='sa-mono' style='font-size:10.5px;font-weight:700;letter-spacing:.5px;color:{c};border:1px solid {c};border-radius:5px;padding:1px 6px'>{t}</span>"


def _crit_badge(crit):
    c = _CRITB.get(crit, "var(--sa-muted)")
    return f"<span class='sa-mono' style='font-size:9.5px;font-weight:700;color:{c};border:1px solid {c};border-radius:5px;padding:1px 5px;opacity:.9'>{_e(crit)}</span>"


# JS-обработчик HITL-кнопок: POST решения form-urlencoded → подмена внутренности инспектора.
# Определяется один раз на странице узла; фрагмент рефреша скрипт не несёт (handler уже на странице).
_HITL_JS = """<script>
function hitlDecide(run, decision){
  var box=document.getElementById('sa-inspector'); if(!box) return;
  var ap=box.querySelector('[name=approver]'), rs=box.querySelector('[name=reason]');
  var reason=rs?rs.value:'';
  if(decision==='reject' && !reason.trim()){ if(rs){rs.focus();rs.style.borderColor='var(--sa-alert)';} return; }
  var body='approver='+encodeURIComponent(ap?ap.value:'')+'&reason='+encodeURIComponent(reason);
  box.style.opacity='.55';
  fetch('/ui/map/run/'+encodeURIComponent(run)+'/'+decision,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:body})
    .then(function(r){return r.text();}).then(function(h){ box.innerHTML=h; box.style.opacity='1'; })
    .catch(function(){ box.style.opacity='1'; });
}
</script>"""


def _hitl_panel(sel_run, detail):
    """Панель решения HITL для критичной версии: «почему требует внимания» (доказательный
    чеклист гейта promote) + принятые решения + кнопки Аппрув/Отклонить с обоснованием."""
    dec = (detail or {}).get("decision") or {}
    if not dec.get("requires_validation"):
        return ""
    state = dec.get("state", "hitl")
    sc, _sl = _RUNSTATE.get(state, _RUNSTATE["hitl"])
    runid = sel_run["id"]
    items = ""
    for g in dec.get("gate", []):
        ok = g["ok"]
        pending = (g["key"] == "hitl" and not ok and state != "rejected")
        if ok:
            ic, col = "bi-check-circle-fill", "var(--sa-ok)"
        elif pending:
            ic, col = "bi-hourglass-split", "var(--sa-warn)"
        else:
            ic, col = "bi-x-circle-fill", "var(--sa-alert)"
        items += (
            "<div style='display:flex;gap:8px;align-items:flex-start;padding:5px 0'>"
            f"<i class='bi {ic}' style='color:{col};font-size:13px;line-height:1.3;flex:none'></i>"
            "<div style='min-width:0'>"
            f"<div style='font-size:11.5px;color:var(--sa-text);font-weight:600'>{_e(g['label'])}</div>"
            f"<div style='font-size:10.5px;color:var(--sa-text2);margin-top:1px'>{_e(g['detail'])}</div></div></div>")
    if dec.get("decisions"):
        rows = ""
        for d in dec["decisions"]:
            appr = d["decision"] == "approve"
            dc = "var(--sa-ok)" if appr else "var(--sa-alert)"
            dt = "аппрув" if appr else "отклонение"
            reason = f" · «{_e(d['reason'])}»" if d.get("reason") else ""
            rows += (
                "<div style='font-size:10.5px;color:var(--sa-text2);padding:4px 0;border-top:1px solid var(--sa-line)'>"
                f"<span class='sa-mono' style='color:{dc};font-weight:700'>{dt}</span> · "
                f"{_e(d['approver'])} <span style='color:var(--sa-accent-ink);font-weight:600'>{_e(d['role'])}</span>"
                f" · <span class='sa-mono'>{_e(d['ts'])}</span>{reason}</div>")
        decisions_block = (
            "<div style='font-size:10px;letter-spacing:1px;text-transform:uppercase;color:var(--sa-muted);font-weight:600;margin:12px 0 2px'>Принятые решения</div>"
            f"{rows}")
    else:
        decisions_block = "<div style='font-size:10.5px;color:var(--sa-muted);margin-top:10px'>решения ещё не принимались</div>"
    if state in ("hitl", "hold", "rejected"):
        opts = "".join(f"<option value='{a}'>{a} · MLSecOps</option>" for a in ("mlsecops", "reviewer"))
        owner = dec.get("owner", "—")
        action = (
            "<div style='margin-top:12px;padding-top:11px;border-top:1px solid var(--sa-line)'>"
            "<div style='font-size:10px;letter-spacing:1px;text-transform:uppercase;color:var(--sa-muted);font-weight:600;margin-bottom:5px'>Решение от имени (MLSecOps)</div>"
            "<select name='approver' class='sa-mono' style='width:100%;background:var(--sa-panel2);color:var(--sa-text);border:1px solid var(--sa-line);border-radius:7px;padding:6px 8px;font-size:11.5px'>"
            f"{opts}</select>"
            "<textarea name='reason' rows='2' placeholder='обоснование (обязательно для отклонения)' "
            "style='width:100%;margin-top:7px;background:var(--sa-panel2);color:var(--sa-text);border:1px solid var(--sa-line);border-radius:7px;padding:7px 8px;font-size:11.5px;font-family:inherit;resize:vertical'></textarea>"
            "<div style='display:flex;gap:8px;margin-top:9px'>"
            f"<button type='button' onclick=\"hitlDecide('{_e(runid)}','approve')\" "
            "style='flex:1;border:none;border-radius:8px;padding:9px;font-size:12px;font-weight:700;cursor:pointer;background:var(--sa-ok);color:#04140d'>"
            "<i class='bi bi-check-lg'></i> Аппрув</button>"
            f"<button type='button' onclick=\"hitlDecide('{_e(runid)}','reject')\" "
            "style='flex:1;border:1px solid var(--sa-alert);border-radius:8px;padding:9px;font-size:12px;font-weight:700;cursor:pointer;background:rgba(239,68,68,.12);color:var(--sa-alert)'>"
            "<i class='bi bi-x-lg'></i> Отклонить</button></div>"
            "<div style='font-size:10px;color:var(--sa-muted);margin-top:8px;line-height:1.45'>"
            f"Аппрувер ≠ владелец (<span class='sa-mono'>{_e(owner)}</span> · DS) и ≠ тот, кто промоутит. "
            "Промоушен выполнит отдельный MLSecOps (separation of duties, ACC-02).</div></div>")
    else:
        action = ("<div style='margin-top:11px;padding-top:10px;border-top:1px solid var(--sa-line);font-size:11px;color:var(--sa-ok)'>"
                  "<i class='bi bi-check2-circle'></i> решение принято — версия в проде</div>")
    blockers = dec.get("blockers", 0)
    sub = (f"{blockers} условие(й) ещё не выполнено" if blockers else "все условия выполнены")
    return (
        f"<div style='border:1px solid var(--sa-line);border-left:3px solid {sc};border-radius:11px;background:var(--sa-panel);padding:12px 14px;margin-bottom:14px'>"
        "<div style='display:flex;align-items:center;justify-content:space-between;gap:8px'>"
        "<span style='font-size:11px;font-weight:700;color:var(--sa-head);display:flex;align-items:center;gap:6px'>"
        f"<i class='bi bi-hand-index-thumb' style='color:{sc}'></i> Требует решения (HITL · VIS-03)</span>"
        f"{_rs_badge(state)}</div>"
        f"<div style='font-size:10.5px;color:var(--sa-text2);margin-top:3px'>Критичная модель уходит в прод только после ручного решения MLSecOps. {_e(sub)}.</div>"
        "<div style='font-size:10px;letter-spacing:1px;text-transform:uppercase;color:var(--sa-muted);font-weight:600;margin:11px 0 2px'>Почему требует внимания</div>"
        f"{items}{decisions_block}{action}</div>")


def _inspector_inner(sel_run, detail):
    """Внутренность правой колонки инспектора (шапка прогона + HITL-панель + lineage +
    сработки + терминальный лог). Выделено, чтобы тем же кодом рендерить HTMX-рефреш."""
    from ..runs import actor_role, role_of
    detail = detail or {}
    if not sel_run:
        return "<div style='padding:18px;color:var(--sa-muted);font-size:13px'>выберите прогон слева</div>"
    acct, role = actor_role(sel_run["actor"])
    lin = detail.get("lineage", {})
    lin_rows = "".join(
        f"<div class='sa-lin'><span class='sa-mono' style='font-size:11px;color:var(--sa-text2)'>{k}</span>"
        f"<span class='sa-mono' style='font-size:11px;color:{'var(--sa-alert)' if v=='—' else 'var(--sa-text)'};text-align:right;word-break:break-all'>{_e(v)}</span></div>"
        for k, v in [("dataset", lin.get("dataset", "—")), ("code_commit", lin.get("code_commit", "—")),
                     ("env_lock", lin.get("env_lock", "—")), ("artifact_hash", lin.get("artifact_hash", "—")),
                     ("signature", lin.get("signature", "—"))])
    dfs = detail.get("findings", [])
    if dfs:
        fcards = ""
        for f in dfs:
            fa, fr = role_of(f)
            sc = _SEVC.get(f["severity"], "var(--sa-muted)")
            fcards += (
                f"<div class='sa-fcard'><div style='display:flex;align-items:center;gap:7px;flex-wrap:wrap'>"
                f"<span class='sa-badge sa-mono' style='color:{sc};background:rgba(148,163,184,.12)'>{_e(f['severity'])}</span>"
                f"<span class='sa-mono' style='font-size:11.5px;font-weight:600;color:{sc}'>{_e(f['verdict'])}</span>"
                f"<span style='flex:1'></span><span class='sa-badge sa-mono' style='color:var(--sa-text2);border:1px solid var(--sa-line)'>{_e(f['status'])}</span></div>"
                f"<div class='sa-mono' style='font-size:10px;color:var(--sa-muted);margin-top:5px'>{_e(f['tool'])} · {_e(f['asset'])}</div>"
                f"<div style='font-size:11.5px;color:var(--sa-text2);margin-top:5px;line-height:1.45'>{_e(f['detail'])}</div>"
                f"<div class='sa-mono' style='font-size:10px;color:var(--sa-text2);margin-top:6px'>причастен: {_e(fa)} "
                f"<span style='color:var(--sa-accent-ink);font-weight:600'>{_e(fr)}</span></div></div>")
    else:
        fcards = "<div style='font-size:12px;color:var(--sa-muted);padding:4px 0'>сработок нет — прогон чист</div>"
    log = detail.get("log", [])
    log_lines = "".join(
        f"<div class='sa-tl'><span class='t'>{_e(l['t'])}</span>"
        f"<span class='src' style='color:{_LVL.get(l['lvl'],'var(--sa-text2)')}'>{_e(l['src'])}</span>"
        f"<span style='color:{_LVL[l['lvl']] if l['lvl'] in ('err','sec') else '#cbd5e1'}'>{_e(l['msg'])}</span></div>"
        for l in log) or "<div style='color:var(--sa-muted);font-size:12px'>// лог пуст</div>"
    tm = detail.get("timing") or {}
    _tp = []
    if tm.get("created"):
        _tp.append(f"заведён {tm['created'].split('T')[-1][:8]}")
    if tm.get("promoted"):
        _tp.append(f"в проде {tm['promoted'].split('T')[-1][:8]}")
    if tm.get("retired"):
        _tp.append(f"выведен {tm['retired'].split('T')[-1][:8]}")
    if tm.get("dur"):
        _tp.append(f"в контуре {tm['dur']}")
    timing_line = (f"<div class='sa-mono' style='font-size:10px;color:var(--sa-muted);margin-top:7px'>{_e(' · '.join(_tp))}</div>"
                   if _tp else "")
    return (
        "<div style='padding:14px 16px;border-bottom:1px solid var(--sa-line);flex:none'>"
        "<div style='display:flex;align-items:center;justify-content:space-between'>"
        "<span style='font-size:10px;letter-spacing:1.4px;text-transform:uppercase;color:var(--sa-text2);font-weight:600'>Инспектор прогона</span>"
        f"{_rs_badge(sel_run['state'])}</div>"
        f"<div style='display:flex;align-items:baseline;gap:8px;margin-top:8px'>"
        f"<span class='sa-mono' style='font-size:16px;font-weight:700;color:var(--sa-head)'>{_e(sel_run['id'])}</span>"
        f"<span style='font-size:13px;color:var(--sa-text)'>{_e(sel_run['model'])} <span class='sa-mono' style='color:var(--sa-text2)'>{_e(sel_run['ver'])}</span></span></div>"
        f"<div style='display:flex;gap:6px;margin-top:8px;flex-wrap:wrap'>{_crit_badge(sel_run['crit'])}"
        f"<span class='sa-chip'>причастен: {_e(acct)} · {_e(role)}</span></div>{timing_line}</div>"
        "<div class='sa-scroll' style='flex:1;overflow-y:auto;padding:12px 16px;min-height:0'>"
        f"{_hitl_panel(sel_run, detail)}"
        "<div style='font-size:10px;letter-spacing:1.2px;text-transform:uppercase;color:var(--sa-muted);font-weight:600;margin-bottom:7px'>Lineage · воспроизводимость (MON-02)</div>"
        f"<div style='border:1px solid var(--sa-line);border-radius:10px;background:var(--sa-panel);overflow:hidden;margin-bottom:14px'>{lin_rows}</div>"
        f"<div style='font-size:10px;letter-spacing:1.2px;text-transform:uppercase;color:var(--sa-muted);font-weight:600;margin-bottom:7px'>Сработки прогона ({len(dfs)})</div>{fcards}</div>"
        "<div style='padding:12px;border-top:1px solid var(--sa-line);flex:none'>"
        f"<div class='sa-term'><div class='sa-term-h'><i style='background:#ef4444'></i><i style='background:#f59e0b'></i><i style='background:#10b981'></i>"
        f"<span class='sa-mono' style='font-size:10.5px;color:var(--sa-text2)'>{_e(sel_run['id'])}.log</span></div>"
        f"<div class='sa-term-b sa-scroll sa-mono' style='max-height:200px'>{log_lines}</div></div></div>")


def map_inspector_fragment(sel_run, detail):
    """HTMX/fetch-фрагмент: внутренность инспектора (рефреш после HITL-решения)."""
    return _inspector_inner(sel_run, detail)


def map_inspector_page(node, pipeline, infra, runs, sel_run, detail):
    """Инспектор узла (stage B): шапка узла + очередь прогонов (ModelVersion) + инспектор
    прогона (lineage MON-02 + сработки с причастным «учётка (роль)» + терминальный лог)."""
    from ..runs import actor_role
    nid = node["id"]
    st = node.get("status", "clean")
    controls = CONTROLS.get(nid, [])
    runs = runs or []
    detail = detail or {}
    pidx = {n["id"]: i for i, n in enumerate(pipeline)}
    sel_id = sel_run["id"] if sel_run else (runs[0]["id"] if runs else None)

    def short_t(ts):
        return (ts or "").split("T")[-1][:8]

    def track(run):
        ri = pidx.get(run["node"], 0)
        segs = ""
        for i in range(len(pipeline)):
            col = "var(--sa-ok)" if i < ri else (_RUNSTATE.get(run["state"], ("var(--sa-muted)",))[0] if i == ri else "var(--sa-line2)")
            glow = f"box-shadow:0 0 6px 0 {col}" if i == ri else ""
            segs += f"<span style='height:4px;flex:1;border-radius:2px;background:{col};{glow}'></span>"
        return f"<div style='display:flex;gap:3px;margin-top:10px'>{segs}</div>"

    # ── очередь прогонов ──
    if runs:
        cards = ""
        for r in runs:
            sel = r["id"] == sel_id
            border = "var(--sa-accent)" if sel else "var(--sa-line)"
            bg = "var(--sa-panel3)" if sel else "var(--sa-panel)"
            shadow = "box-shadow:0 4px 18px -8px rgba(250,204,21,.4)" if sel else ""
            fc = (f"<span class='sa-mono' style='font-size:11px;color:var(--sa-warn)'>● {r['findings']}</span>"
                  if r["findings"] else "<span class='sa-mono' style='font-size:11px;color:var(--sa-ok)'>clean</span>")
            cards += (
                f"<a class='sa-runcard' href='/map/node/{_e(nid)}?run={_e(r['id'])}' style='border-color:{border};background:{bg};{shadow}'>"
                f"<div style='display:flex;align-items:center;gap:9px;flex-wrap:wrap'>{_rs_badge(r['state'])}"
                f"<span class='sa-mono' style='font-size:12.5px;font-weight:700;color:var(--sa-head)'>{_e(r['id'])}</span>"
                f"<span style='font-size:12.5px;color:var(--sa-text)'>{_e(r['model'])} <span class='sa-mono' style='color:var(--sa-text2)'>{_e(r['ver'])}</span></span>"
                f"{_crit_badge(r['crit'])}<span style='flex:1'></span>{fc}</div>{track(r)}"
                f"<div style='display:flex;justify-content:space-between;margin-top:7px'>"
                f"<span class='sa-mono' style='font-size:10.5px;color:var(--sa-text2)'>@ {_e(SHORT.get(r['node'], r['node']))}</span>"
                f"<span class='sa-mono' style='font-size:10.5px;color:var(--sa-muted)'>start {_e(short_t(r['started']))} · {_e(r['dur'])} · {_e(r['actor'])}</span></div></a>")
    else:
        cards = "<div style='font-size:12px;color:var(--sa-muted);padding:8px 2px'>прогонов в контуре нет</div>"

    # ── инспектор прогона (правая колонка) — тем же кодом, что и HTMX-рефреш ──
    inspector = _inspector_inner(sel_run, detail)

    gate_tag = ("<span class='sa-mono' style='font-size:8.5px;font-weight:800;color:var(--sa-bg);background:var(--sa-accent);border-radius:4px;padding:2px 6px'>FAIL-CLOSED</span>"
                if node.get("gate") else "")
    prev_tag = "<span class='sa-chip'>preventive</span>" if nid in PREVENTIVE else ""
    chips = "".join(f"<span class='sa-chip'>{_e(c)}</span>" for c in controls) or "<span style='font-size:11.5px;color:var(--sa-muted)'>инфраструктурный узел контура</span>"
    qtitle = "Прогоны на узле" if nid in {"package", "validate", "serving", "decommission", "gate-artifact"} else "Очередь прогонов контура"
    ncolor = _SC.get(st, "var(--sa-muted)")
    nopen = node.get("open") or 0
    nhealth = (f"<span class='sa-mono' style='color:{ncolor};font-weight:700'>● {nopen} откр.</span>"
               if nopen else "<span class='sa-mono' style='color:var(--sa-ok)'>чисто</span>")
    content = (
        "<div style='display:flex;flex-direction:column;height:100%'>"
        # шапка узла — индикатор = ЗДОРОВЬЕ УЗЛА (его открытые сработки), не движение прогона
        "<div style='flex:none;padding:14px 22px 13px;border-bottom:1px solid var(--sa-line);background:var(--sa-panel2)'>"
        "<div style='display:flex;align-items:center;gap:10px;flex-wrap:wrap'>"
        f"<span class='sa-led' style='width:12px;height:12px;--c:{ncolor}' title='здоровье узла'></span>"
        f"<h2 style='margin:0;font-size:18px;font-weight:700;color:var(--sa-head)'>{_e(node['label'])}</h2>{gate_tag}{prev_tag}"
        f"<span style='flex:1'></span><span style='font-size:11.5px;color:var(--sa-text2)'>здоровье узла: {nhealth} "
        f"<span style='color:var(--sa-line2)'>·</span> {len(runs)} прогон(ов) · {len(controls)} контролей</span></div>"
        f"<div style='display:flex;flex-wrap:wrap;gap:6px;margin-top:10px'>{chips}</div>"
        "<div style='font-size:10px;color:var(--sa-muted);margin-top:8px;line-height:1.4'>Индикатор узла — его собственные открытые сработки "
        "(здоровье узла), независимо от потока. Движение прогонов по конвейеру ЖЦ — в очереди и треке ниже.</div></div>"
        # тело: очередь + инспектор
        "<div style='flex:1;min-height:0;display:flex;overflow:hidden'>"
        "<div style='flex:1;min-width:0;display:flex;flex-direction:column;overflow:hidden'>"
        f"<div style='padding:12px 18px 1px;font-size:10.5px;letter-spacing:1.2px;text-transform:uppercase;color:var(--sa-text2);font-weight:600'>{qtitle}</div>"
        "<div style='padding:0 18px 6px;font-size:10px;color:var(--sa-muted)'>трек — прохождение прогона по потоку ЖЦ; бейдж слева — состояние прогона</div>"
        f"<div class='sa-scroll' style='flex:1;overflow-y:auto;padding:4px 16px 16px'>{cards}</div></div>"
        "<div style='width:384px;flex:none;border-left:1px solid var(--sa-line);background:var(--sa-panel2);display:flex;flex-direction:column;overflow:hidden'>"
        f"<div id='sa-inspector' style='display:flex;flex-direction:column;height:100%;min-height:0'>{inspector}</div></div></div></div>"
        f"{_HITL_JS}"
    )
    breadcrumb = (
        "<a class='sa-back' href='/map'><i class='bi bi-arrow-left'></i> Обзор</a>"
        "<i class='bi bi-chevron-right' style='color:var(--sa-line2);font-size:11px'></i>"
        f"<span class='sa-led' style='width:9px;height:9px;--c:{_SC.get(st,'var(--sa-muted)')}'></span>"
        f"<span class='h'>{_e(node['label'])}</span>{gate_tag}"
    )
    return _shell(nid, pipeline, infra, breadcrumb, content, title=f"Sirius Argus — {node['label']}")


# ── legacy-фрагменты drill (используются /ui/map/node, /ui/map/incident) ──
def map_node_fragment(node_id, label, controls, findings, audit_rows):
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
        ftable = "<div class='p-3 text-slate-400 text-sm'>сработок по узлу нет</div>"
    audit_html = audit_fragment(audit_rows) if audit_rows else "<div class='p-3 text-slate-400 text-sm'>событий нет</div>"
    drill_js = ("<script>function drillIncident(id){"
                "if(window.htmx){htmx.ajax('GET','/ui/map/incident/'+id,'#map-incident');}"
                "else{fetch('/ui/map/incident/'+id).then(r=>r.text()).then(h=>{document.getElementById('map-incident').innerHTML=h;});}}</script>")
    return (f"<div class='mb-3 flex flex-wrap gap-1'>{ctl}</div>"
            f"<div class='rounded-lg border border-slate-200 overflow-hidden mb-4'>{ftable}</div>"
            f"{drill_js}<div id='map-incident' class='mt-4'></div>")


def map_incident_fragment(finding, audit_rows):
    from .layout import _SEV, _STATUS
    if not finding:
        return "<div class='p-3 text-slate-400 text-sm'>сработка не найдена</div>"
    f = finding
    head = (f"<div class='flex items-center gap-2 mb-2'><span class='px-2 py-0.5 rounded text-xs {_SEV.get(f['severity'], 'bg-slate-100')}'>{_e(f['severity'])}</span>"
            f"<b>{_e(f['verdict'])}</b><span class='text-slate-400 text-xs'>· {_e(f['tool'])} · {_e(f['ts'])}</span></div>")
    from ..runs import role_of
    acct, role = role_of(f)
    meta = (f"<div class='text-sm text-slate-600 mb-1'>Актив: <span class='font-mono text-xs'>{_e(f['asset'])}</span></div>"
            f"<div class='text-sm text-slate-600 mb-1'>Причастен: <b>{_e(acct)}</b> "
            f"<span class='font-mono text-xs text-amber-600'>{_e(role)}</span></div>"
            f"<div class='text-sm text-slate-600 mb-3'>Что произошло: {_e(f['detail'])}</div>")
    tl = audit_fragment(audit_rows) if audit_rows else "<div class='p-3 text-slate-400 text-sm'>событий нет</div>"
    return ("<div class='rounded-xl border-2 border-slate-300 bg-slate-50 p-4'><h3 class='font-semibold mb-1'>Инцидент</h3>"
            f"{head}{meta}<div class='rounded-lg border border-slate-200 bg-white overflow-hidden'>{tl}</div></div>")
