"""pytest-bdd: сквозной ЖЦ одной модели (И6) — приём→gate→HITL→деплой→атака→decommission."""
import os
import pickle
import time

import httpx
from pytest_bdd import given, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
SERVING = os.environ.get("SERVING_URL", "http://localhost:8001")
scenarios("pipeline.feature")
S = {}


def tok(role):
    return {"Authorization": f"Bearer dev:{role.lower()}:{role}"}


class _Evil:
    def __reduce__(self):
        return (os.system, ("echo sirius-demo-marker",))  # безвреден, не исполняется


@given("поднятый стек (control-plane и сервинг)")
def up():
    assert httpx.get(f"{BASE}/health", timeout=60).status_code == 200, "сначала `DEV_AUTH=1 make up`"
    assert httpx.get(f"{SERVING}/health", timeout=60).status_code == 200, "сервинг не поднят"


@when("модель проходит полный жизненный цикл")
def lifecycle():
    dv = httpx.post(f"{BASE}/api/datasets", headers=tok("DE"),
                    json={"name": "loans", "sensitivity": "open", "source": "internal://curated/loans"}, timeout=60).json()["dataset_version_id"]
    mid = httpx.post(f"{BASE}/api/models", headers=tok("DS"),
                     json={"name": "loan-scoring", "type": "boosting", "criticality": "financial"}, timeout=60).json()["model_id"]
    # 1) вредоносный приём → блок
    S["mal"] = httpx.post(f"{BASE}/api/models/{mid}/ingest", headers=tok("DS"), content=pickle.dumps(_Evil()), timeout=60).status_code
    # 2) документированная версия (lineage + карта + подпись)
    ver = httpx.post(f"{BASE}/api/models/{mid}/versions", headers=tok("DS"),
                     json={"dataset_version_id": dv, "code_commit": "abc123", "env_lock": "req.lock",
                           "intended_use": "скоринг", "limitations": "не для физлиц"}, timeout=60).json()["version"]
    httpx.post(f"{BASE}/api/models/{mid}/versions/{ver}/sign", headers=tok("MLSecOps"), timeout=60)  # крипто-подпись (SUP-04)
    # 3) promote без HITL → блок
    S["promote_no_hitl"] = httpx.post(f"{BASE}/api/models/{mid}/versions/{ver}/promote", headers=tok("MLSecOps"), timeout=60).status_code
    # 4) аппрув другим MLSecOps (reviewer) + promote → прод
    httpx.post(f"{BASE}/api/models/{mid}/versions/{ver}/approve",
               headers={"Authorization": "Bearer dev:reviewer:MLSecOps"}, json={"reason": "валидация ок"}, timeout=60)
    S["promote_hitl"] = httpx.post(f"{BASE}/api/models/{mid}/versions/{ver}/promote", headers=tok("MLSecOps"), timeout=60).status_code
    # 5) инференс (уникальный client-id — изоляция от бёрстов по host-IP).
    #    На 503 (глобальный load-shed после флуд-тестов DOS-01) клиент отступает и повторяет.
    for _ in range(15):
        S["predict"] = httpx.post(f"{SERVING}/predict/iris-linear", headers={"X-Client-Id": "pipeline-test"},
                                  json={"features": [5.1, 3.5, 1.4, 0.2]}, timeout=60).status_code
        if S["predict"] != 503:
            break
        time.sleep(1)
    # 6) decommission + запрет отката
    S["retire"] = httpx.post(f"{BASE}/api/models/{mid}/versions/{ver}/retire", headers=tok("MLSecOps"), timeout=60).status_code
    S["promote_retired"] = httpx.post(f"{BASE}/api/models/{mid}/versions/{ver}/promote", headers=tok("MLSecOps"), timeout=60).status_code


@then("вредоносный приём заблокирован, а версия проходит HITL и деплоится")
def gates_ok():
    assert S["mal"] == 422, S
    assert S["promote_no_hitl"] == 422, S
    assert S["promote_hitl"] == 200, S
    assert S["predict"] == 200, S


@then("вывод из эксплуатации снимает версию и запрещает откат")
def decommission_ok():
    assert S["retire"] == 200, S
    assert S["promote_retired"] == 409, S
