"""ui.decisions — реестр решений ручного аппрув-гейта (дизайн-язык SA)."""
from .layout import _e, _page


def _decision_badge(decision):
    """Бейдж решения: approve → ok «аппрув», reject → alert «отклонение»."""
    if decision == "approve":
        col, lbl = "var(--sa-ok)", "аппрув"
    else:
        col, lbl = "var(--sa-alert)", "отклонение"
    return (f"<span class='sa-badge' "
            f"style='color:{col};background:color-mix(in srgb,{col} 15%,transparent)'>"
            f"{_e(lbl)}</span>")


def _actor(name, role):
    """Имя актора + роль (accent-ink, полужирный) — единый формат для гейта и GRC."""
    return (f"{_e(name)} "
            f"<span class='sa-mono' style='color:var(--sa-accent-ink);font-weight:600;font-size:11.5px'>"
            f"{_e(role)}</span>")


def decisions_page(decisions, risks, kpi):
    """Governance system-of-record: журнал решений ручного аппрув-гейта (VIS-03)
    и принятий остаточного риска (GRC, GOV-02) поверх append-only аудита."""
    reject = kpi.get("reject", 0)
    risk = kpi.get("risk", 0)
    reject_col = "var(--sa-alert)" if reject > 0 else "var(--sa-muted)"
    risk_col = "#fb923c" if risk > 0 else "var(--sa-muted)"
    kpis = (
        f"<div class='sa-kpi'><div class='l'>Решений</div>"
        f"<div class='v'>{_e(kpi.get('total', 0))}</div></div>"
        f"<div class='sa-kpi' style='border-color:var(--sa-ok)'><div class='l'>Аппрувов</div>"
        f"<div class='v' style='color:var(--sa-ok)'>{_e(kpi.get('approve', 0))}</div></div>"
        f"<div class='sa-kpi'><div class='l'>Отклонений</div>"
        f"<div class='v' style='color:{reject_col}'>{_e(reject)}</div></div>"
        f"<div class='sa-kpi'><div class='l'>Принятий риска</div>"
        f"<div class='v' style='color:{risk_col}'>{_e(risk)}</div></div>"
    )

    # ── Panel 1: решения аппрув-гейта ──
    if not decisions:
        panel1 = ("<div class='sa-panel' style='padding:18px;color:var(--sa-muted)'>"
                  "решений ещё не было</div>")
    else:
        rows = ""
        for d in decisions:
            mid = d.get("model_id")
            model = d.get("model", "")
            version = d.get("version", "")
            if mid is not None:
                model_cell = (f"<a class='sa-mono' style='color:var(--sa-blue);text-decoration:none' "
                              f"href='/registry/model/{_e(mid)}'>{_e(model)}</a> v{_e(version)}")
            else:
                model_cell = f"{_e(model)} v{_e(version)}"
            reason = d.get("reason") or ""
            if reason:
                reason_cell = (f"<span style='color:var(--sa-text2)'>{_e(reason)}</span>")
            else:
                reason_cell = "<span style='color:var(--sa-muted)'>—</span>"
            rows += (
                "<tr>"
                f"<td>{_decision_badge(d.get('decision'))}</td>"
                f"<td style='color:var(--sa-text);white-space:nowrap'>{model_cell}</td>"
                f"<td style='color:var(--sa-text)'>{_actor(d.get('approver', ''), d.get('role', ''))}</td>"
                f"<td class='sa-mono' style='color:var(--sa-muted);font-size:11.5px;white-space:nowrap'>{_e(d.get('ts', ''))}</td>"
                f"<td style='max-width:360px'>{reason_cell}</td>"
                "</tr>")
        panel1 = ("<div class='sa-panel'><table class='sa-table'><thead><tr>"
                  "<th>решение</th><th>модель · версия</th><th>аппрувер</th>"
                  "<th>время</th><th>обоснование</th>"
                  f"</tr></thead><tbody>{rows}</tbody></table></div>")

    # ── Panel 2: принятия остаточного риска (GOV-02) — только если risks непуст ──
    panel2 = ""
    if risks:
        rrows = ""
        for r in risks:
            active = r.get("active")
            if active:
                status = ("<span class='sa-badge' "
                          "style='color:var(--sa-ok);background:color-mix(in srgb,var(--sa-ok) 15%,transparent)'>"
                          "активно</span>")
            else:
                status = ("<span class='sa-badge' "
                          "style='color:var(--sa-muted);background:color-mix(in srgb,var(--sa-muted) 15%,transparent)'>"
                          "снято</span>")
            rrows += (
                "<tr>"
                f"<td style='color:var(--sa-text)'>{_e(r.get('scope', ''))}</td>"
                f"<td class='sa-mono' style='color:var(--sa-text2);font-size:11.5px;white-space:nowrap'>{_e(r.get('ref', ''))}</td>"
                f"<td style='color:var(--sa-text)'>{_actor(r.get('by', ''), r.get('role', ''))}</td>"
                f"<td class='sa-mono' style='color:var(--sa-muted);font-size:11.5px;white-space:nowrap'>{_e(r.get('ts', ''))}</td>"
                f"<td style='color:var(--sa-text2);max-width:280px'>{_e(r.get('justification', ''))}</td>"
                f"<td style='color:var(--sa-text2);max-width:220px'>{_e(r.get('conditions', ''))}</td>"
                f"<td class='sa-mono' style='color:var(--sa-text2);font-size:11.5px;white-space:nowrap'>{_e(r.get('expires', ''))}</td>"
                f"<td>{status}</td>"
                "</tr>")
        panel2 = (
            "<div class='sa-eye' style='margin-top:26px'>принятия остаточного риска (GOV-02)</div>"
            "<div class='sa-panel'><table class='sa-table'><thead><tr>"
            "<th>область</th><th>объект</th><th>кем</th><th>время</th>"
            "<th>обоснование</th><th>условия</th><th>срок</th><th>статус</th>"
            f"</tr></thead><tbody>{rrows}</tbody></table></div>")

    body = (
        "<div class='sa-eye'>Sirius Argus · реестр решений</div>"
        "<h1 class='sa-h1'>Реестр решений</h1>"
        "<p class='sa-sub'>Журнал решений ручного аппрув-гейта "
        "(<span class='sa-mono' style='color:var(--sa-accent-ink)'>VIS-03</span>): кто и когда "
        "аппрувил или отклонял критичную версию перед промоушеном — и с каким обоснованием. "
        "Сюда же попадают принятия остаточного риска (GRC, "
        "<span class='sa-mono' style='color:var(--sa-accent-ink)'>GOV-02</span>). "
        "Governance system-of-record поверх append-only аудита.</p>"
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:16px 0'>"
        f"{kpis}</div>"
        "<div class='sa-eye' style='margin-top:22px'>решения аппрув-гейта</div>"
        f"{panel1}"
        f"{panel2}"
    )
    return _page("Sirius Argus — реестр решений", body, "decisions")
