"""pytest-bdd: GOV-03 — промоушен атомарен (TOCTOU-safe, без дубль-деплоя).

Из security-review: между проверкой стадии и записью stage="prod" не было блокировки —
два параллельных запроса могли пройти гейт и оба создать активный Deployment. Здесь
бьём по версии пачкой одновременных промоушенов и требуем ровно один деплой: блокировка
строки (FOR UPDATE) + state-machine (dev→prod однократно) сериализуют переход.
"""
import concurrent.futures
import os

import httpx
from pytest_bdd import given, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
scenarios("promote_atomic.feature")
S = {}


def tok(role):
    return {"Authorization": f"Bearer dev:{role.lower()}:{role}"}


@given("воспроизводимая версия, готовая к промоушену")
def reproducible_version():
    dv = httpx.post(f"{BASE}/api/datasets", headers=tok("DE"),
                    json={"name": "atom", "sensitivity": "open", "source": "internal://curated/atom"},
                    timeout=10).json()["dataset_version_id"]
    m = httpx.post(f"{BASE}/api/models", headers=tok("DS"),
                   json={"name": "atom", "type": "boosting", "criticality": "internal"},
                   timeout=10).json()["model_id"]
    v = httpx.post(f"{BASE}/api/models/{m}/versions", headers=tok("DS"),
                   json={"dataset_version_id": dv, "code_commit": "abc123", "env_lock": "req.lock"},
                   timeout=10).json()["version"]
    S.update(model_id=m, ver=v, dv=dv)


@when("несколько запросов одновременно промоутят одну версию")
def concurrent_promote():
    def _p(_):
        return httpx.post(f"{BASE}/api/models/{S['model_id']}/versions/{S['ver']}/promote",
                          headers=tok("MLSecOps"), timeout=20).status_code
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        S["codes"] = list(ex.map(_p, range(8)))


@then("ровно один промоушен успешен, остальные отклонены")
def one_success():
    ok = [c for c in S["codes"] if c == 200]
    assert len(ok) == 1, f"ожидали ровно 1 успешный промоушен, коды: {S['codes']}"
    assert all(c in (200, 409) for c in S["codes"]), f"неожиданные коды: {S['codes']}"


@then("активный Deployment у версии ровно один")
def one_deployment():
    imp = httpx.get(f"{BASE}/api/impact", params={"dataset_version_id": S["dv"]},
                    headers=tok("MLSecOps"), timeout=10).json()
    aff = [a for a in imp["affected"] if a["version"] == S["ver"]]
    assert aff and aff[0]["active_deployments"] == 1, f"ожидали ровно 1 активный деплой: {imp}"
