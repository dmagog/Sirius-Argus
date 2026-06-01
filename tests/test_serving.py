"""pytest-bdd: сервинг трио моделей + RT-01 (extraction-detect → throttle + Finding)."""
import os

import httpx
from pytest_bdd import given, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
SERVING = os.environ.get("SERVING_URL", "http://localhost:8001")
scenarios("serving.feature")
S = {}


def tok(role):
    return {"Authorization": f"Bearer dev:{role.lower()}:{role}"}


@given("поднятый сервинг")
def serving_up():
    assert httpx.get(f"{SERVING}/health", timeout=10).status_code == 200, "сначала `make up` (serving)"


@then("доступны 3 модели разных типов")
def three_models():
    j = httpx.get(f"{SERVING}/models", timeout=10).json()
    types = {m["type"] for m in j["models"]}
    assert len(j["models"]) >= 3 and len(types) >= 3, j


@then("каждая модель отвечает на предсказание")
def each_predicts():
    for m in httpx.get(f"{SERVING}/models", timeout=10).json()["models"]:
        r = httpx.post(f"{SERVING}/predict/{m['name']}", json={"features": [0.1, 0.2, 0.3, 0.4]}, timeout=10)
        assert r.status_code == 200 and "prediction" in r.json(), r.text


@when("клиент шлёт бёрст инференс-запросов")
def burst():
    last = None
    for _ in range(60):
        last = httpx.post(f"{SERVING}/predict/credit-linear", headers={"X-Client-Id": "attacker-001"},
                          json={"features": [0.1, 0.2, 0.3, 0.4]}, timeout=10)
    S["last"] = last


@then("сервинг троттлит запросы со статусом 429")
def throttled():
    assert S["last"].status_code == 429, S["last"].text


@then("в control-plane появляется сработка extraction")
def extraction_finding():
    r = httpx.get(f"{BASE}/api/findings", headers=tok("MLSecOps"), timeout=10)
    assert any(f["verdict"] == "extraction" and f["asset"].startswith("endpoint/")
               for f in r.json()["findings"]), r.text
