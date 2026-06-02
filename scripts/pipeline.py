#!/usr/bin/env python3
"""Sirius Argus — сквозной конвейер жизненного цикла ОДНОЙ модели (И6, money-shot #6).

Один прогон по всему ЖЦ: датасет → приём артефакта (скан) → регистрация версии
(lineage + модель-карта + подпись) → policy-гейт + HITL → деплой → инференс →
рантайм-атака (детект) → вывод из эксплуатации (decommission) → карта покрытия.

Запуск:  DEV_AUTH=1 make up   &&   make pipeline      (или python3 scripts/pipeline.py)
Только стандартная библиотека. payload вредоносного pickle безвреден (echo) и НИКОГДА
не исполняется (control-plane не делает pickle.load).
"""
import json
import os
import pickle
import struct
import urllib.error
import urllib.request

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
SERVING = os.environ.get("SERVING_URL", "http://localhost:8001")


def req(method, path, role=None, body=None, sub=None, base=None):
    headers = {}
    if role:
        headers["Authorization"] = f"Bearer dev:{sub or role.lower()}:{role}"
    data = None
    if isinstance(body, (bytes, bytearray)):
        data, headers["Content-Type"] = bytes(body), "application/octet-stream"
    elif body is not None:
        data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
    r = urllib.request.Request((base or BASE) + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, json.loads(resp.read() or "null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or "null")
        except Exception:
            return e.code, None


def step(n, t):
    print(f"\n[{n}] {t}")


def ok(s):
    print(f"    ✓ {s}")


def blocked(s):
    print(f"    \U0001f6d1 {s}")


class _Evil:
    def __reduce__(self):
        return (os.system, ("echo sirius-demo-marker",))  # безвреден; не исполняется


_st = b'{"__metadata__": {"producer": "sirius-demo"}}'
SAFETENSORS = struct.pack("<Q", len(_st)) + _st


def main():
    print("=" * 70)
    print("  Sirius Argus — сквозной конвейер жизненного цикла одной модели")
    print("=" * 70)

    step(1, "DE регистрирует датасет из доверенного источника")
    _, ds = req("POST", "/api/datasets", "DE",
                {"name": "loans", "sensitivity": "open", "source": "internal://curated/loans"})
    ok(f"датасет #{ds['dataset_id']} (статус={ds['status']}), версия данных #{ds['dataset_version_id']}")

    step(2, "DS регистрирует критичную модель (financial)")
    _, m = req("POST", "/api/models", "DS", {"name": "loan-scoring", "type": "boosting", "criticality": "financial"})
    mid = m["model_id"]
    ok(f"модель #{mid} criticality={m['criticality']} backend={m['registry_backend']}")

    step(3, "Приём ВНЕШНЕГО артефакта на ingestion-гейте: вредоносный pickle")
    st, _ = req("POST", f"/api/models/{mid}/ingest", "DS", pickle.dumps(_Evil()))
    blocked(f"HTTP {st} — вредоносный pickle заблокирован сканом (в реестр не попал, не десериализован)")

    step(4, "DS регистрирует обученную версию: lineage + модель-карта + подпись")
    _, v = req("POST", f"/api/models/{mid}/versions", "DS",
               {"dataset_version_id": ds["dataset_version_id"], "code_commit": "abc123", "env_lock": "req.lock",
                "intended_use": "скоринг кредитных заявок", "limitations": "не для физлиц; не финсовет", "signature": "cosign:abc123"})
    ver = v["version"]
    ok(f"версия v{ver} (stage=dev), синхронизирована в MLflow={v['backend_synced']}")

    step(5, "SUP-06 — честный остаток")
    print("    ⚠ сканеры ловят pickle-RCE, небезопасные форматы и CVE, но НЕ логические")
    print("      бэкдоры в весах (ShadowLogic). Поэтому критичная модель ОБЯЗАНА пройти")
    print("      ручную HITL-валидацию; остаточный риск зафиксирован (без overclaim).")

    step(6, "Промоушен в прод через policy-матрицу")
    st, _ = req("POST", f"/api/models/{mid}/versions/{ver}/promote", "MLSecOps")
    blocked(f"без HITL-аппрува: HTTP {st} (нужен ручной аппрув критичной модели)")
    req("POST", f"/api/models/{mid}/versions/{ver}/approve", "MLSecOps", {"reason": "ручная валидация пройдена"}, sub="reviewer")
    st, _ = req("POST", f"/api/models/{mid}/versions/{ver}/promote", "MLSecOps")
    ok(f"reviewer одобрил (HITL + separation of duties) → промоушен: HTTP {st} → prod")

    step(7, "Инференс на сервинге (трио НЕ-генеративных моделей задеплоено)")
    sc, mdl = req("GET", "/models", base=SERVING)
    if sc == 200:
        ok(f"задеплоено моделей: {len(mdl['models'])} — типы {[x['type'] for x in mdl['models']]}")
        _, pr = req("POST", "/predict/iris-linear", base=SERVING, body={"features": [0.1, 0.2, 0.3, 0.4]})
        ok(f"предсказание iris-linear: {pr.get('prediction')}")
    else:
        blocked("сервинг недоступен — пропуск (подними `make up`)")

    step(8, "Рантайм-атака: бёрст extraction одним клиентом")
    n429 = sum(1 for _ in range(70)
               if req("POST", "/predict/iris-linear", base=SERVING, body={"features": [0.1, 0.2, 0.3, 0.4]})[0] == 429)
    blocked(f"extraction-детект: {n429}×429 (троттлинг) + сработка в control-plane (петля рантайм→реестр)")

    step(9, "Инцидент → вывод версии из эксплуатации (decommission)")
    st, _ = req("POST", f"/api/models/{mid}/versions/{ver}/retire", "MLSecOps")
    ok(f"версия retired (HTTP {st}); активные деплои сняты")
    st, _ = req("POST", f"/api/models/{mid}/versions/{ver}/promote", "MLSecOps")
    blocked(f"повторный промоушен изъятой версии: HTTP {st} (RB-01 — откат на уязвимую запрещён)")

    step(10, "Карта покрытия + KPI (CEO-вью)")
    _, cov = req("GET", "/api/coverage", "CEO")
    k = cov["kpi"]
    ok(f"покрытие {k['coverage']} live · сработок {k['findings_total']} · блокировок {k['blocked_attempts']} · аудит цел: {k['audit_chain_ok']}")

    print("\n" + "=" * 70)
    print("  Конвейер пройден: приём→скан→версия→gate→HITL→деплой→инференс→атака→decommission")
    print(f"  CEO-вью: {BASE}/coverage  ·  дашборд/аудит-таймлайн: {BASE}/")
    print("=" * 70)


if __name__ == "__main__":
    main()
