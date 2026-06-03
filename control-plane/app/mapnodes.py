"""Карта пайплайна — узлы и маппинг Finding→узел (ADR-0011, docs/design/map-screen.md).

Единый источник истины для /api/map/status и drill: и статус узлов, и проваливание
используют node_of(). Чистый модуль без БД — зовётся из main.py.
"""

# Пайплайн (порядок слева→направо). is_gate=True → узел-гейт (◇).
PIPELINE = [
    ("intake", "Приём данных", False),
    ("gate-data", "Гейт данных", True),
    ("train", "Обучение", False),
    ("package", "Упаковка / Реестр", False),
    ("gate-artifact", "Гейт артефакта", True),
    ("validate", "Валидация / HITL", True),
    ("gate-ci", "CI-гейт", True),
    ("serving", "Сервинг", False),
    ("monitor", "Мониторинг", False),
    ("decommission", "Вывод", False),
]

INFRA = [
    ("control-plane", "Control-plane"),
    ("mlflow", "MLflow"),
    ("minio", "MinIO"),
    ("gitea", "Gitea"),
    ("postgres", "Postgres · Аудит"),
    ("keycloak", "Keycloak"),
    ("vault", "Vault"),
    ("bus", "Шина · Observability"),
]

LABELS = {nid: lbl for nid, lbl, *_ in PIPELINE}
LABELS.update({nid: lbl for nid, lbl in INFRA})
ALL_NODES = [nid for nid, *_ in PIPELINE] + [nid for nid, _ in INFRA]

# Короткие подписи для узлов графа обзора (узкие плитки).
SHORT = {
    "intake": "Приём", "gate-data": "Гейт данных", "train": "Обучение", "package": "Упаковка",
    "gate-artifact": "Гейт артеф.", "validate": "Валидация", "gate-ci": "CI-гейт",
    "serving": "Сервинг", "monitor": "Монитор", "decommission": "Вывод",
    "control-plane": "Control-plane", "mlflow": "MLflow", "minio": "MinIO", "gitea": "Gitea",
    "postgres": "Postgres", "keycloak": "Keycloak", "vault": "Vault", "bus": "Шина",
}

# Превентивные узлы: зелёные без сработок = «armed» (контроль работает молча, не порождает Finding).
PREVENTIVE = {"validate", "keycloak", "vault", "intake", "train", "package", "decommission"}

# Активные контроли по узлам — для шапки drill-панели.
CONTROLS = {
    "gate-data": ["sensitivity-классификация", "trusted-source", "качество + карантин (DATA-01/02)"],
    "gate-artifact": ["modelaudit/modelscan (SUP-01)", "подпись + провенанс (SUP-04/05)", "SBOM"],
    "validate": ["HITL-аппрув критичных (VIS-03)", "ART / red-team"],
    "gate-ci": ["dep-scan CVE (SUP-03)", "gitleaks (ACC-06)", "Semgrep (CODE-01)", "branch protection (GT-1)"],
    "serving": ["rate-limit / extraction (RT-01)", "load-shedding (DOS-01)", "OOD/adversarial (RT-02)",
                "drift (MON-01)", "output-reduction (RT-03/04)", "сегментация рантайма (RT-06)"],
    "monitor": ["drift-монитор (MON-01)", "переоценка метрик"],
    "decommission": ["retire + отзыв доступов (MON-03)"],
    "train": ["lineage / воспроизводимость (MON-02)"],
    "package": ["реестр версий + стадии"],
    "intake": ["приём датасета → карантин-гейт"],
    "control-plane": ["zero-trust RBAC (ACC-01)", "object-authz (ESC-01)", "единая точка входа"],
    "mlflow": ["доступ только через CP (REG-01)", "integrity метаданных"],
    "minio": ["scoped keys", "private-by-default"],
    "gitea": ["единая точка входа в прод", "webhook HMAC (GT-3)"],
    "postgres": ["append-only + hash-chain аудита (MON-04 / LOG-02)"],
    "keycloak": ["OIDC fail-closed (AUTH-01)", "short-lived токены (CRED-01)",
                 "единый вход в ops-консоли: Grafana/Gitea (SSO, ADR-0012)"],
    "vault": ["AppRole-выдача секретов + аудит"],
    "bus": ["auth клиентов + ACL топиков (EVT-01)"],
}


def node_of(verdict="", tool="", asset_type="", asset_ref=""):
    """Какому узлу карты принадлежит сработка. Порядок правил важен (специфичное → общее)."""
    v = (verdict or "").lower()
    t = (tool or "").lower()
    at = (asset_type or "").lower()
    ar = (asset_ref or "").lower()
    if t == "sirius-ingress":                       # oversized-upload и пр. на периметре CP
        return "control-plane"
    if v == "drift":
        return "monitor"
    if t in ("modelaudit", "modelscan", "picklescan", "fickling"):
        return "gate-artifact"
    if v in ("unsigned", "signature-mismatch", "artifact-tamper") or (v == "malicious" and at == "model"):
        return "gate-artifact"
    if at == "dataset" or v in ("label-anomaly", "label-distribution-anomaly", "poisoning", "untrusted-source"):
        return "gate-data"
    if at == "pr" or v in ("cve", "secret", "sast", "ci-supply-chain", "hardcoded-logic"):
        return "gate-ci"
    if t == "sirius-runtime" or at == "endpoint" or ar.startswith("endpoint/"):
        return "serving"
    if v == "registry-tamper":
        return "mlflow"
    if v == "audit-tamper":
        return "postgres"
    if v in ("token-misuse", "auth-fail"):
        return "keycloak"
    if v in ("access-denied", "idor", "privesc"):
        return "control-plane"
    if v == "event-integrity":
        return "bus"
    if v in ("hitl-required", "promotion-blocked"):
        return "validate"
    return "control-plane"
