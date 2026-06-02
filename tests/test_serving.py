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
    # уникальный client-id — изоляция от бёрстов demo/pipeline по host-IP (rate-limit)
    h = {"X-Client-Id": "serving-each-test"}
    for m in httpx.get(f"{SERVING}/models", timeout=10).json()["models"]:
        r = httpx.post(f"{SERVING}/predict/{m['name']}", headers=h, json={"features": [5.1, 3.5, 1.4, 0.2]}, timeout=10)
        assert r.status_code == 200 and "prediction" in r.json(), r.text


@when("клиент шлёт бёрст инференс-запросов")
def burst():
    last = None
    for _ in range(60):
        last = httpx.post(f"{SERVING}/predict/iris-linear", headers={"X-Client-Id": "attacker-001"},
                          json={"features": [5.1, 3.5, 1.4, 0.2]}, timeout=10)
    S["last"] = last


@then("сервинг троттлит запросы со статусом 429")
def throttled():
    assert S["last"].status_code == 429, S["last"].text


@then("в control-plane появляется сработка extraction")
def extraction_finding():
    r = httpx.get(f"{BASE}/api/findings", headers=tok("MLSecOps"), timeout=10)
    assert any(f["verdict"] == "extraction" and f["asset"].startswith("endpoint/")
               for f in r.json()["findings"]), r.text


@when("на инференс приходит аномальный (OOD) вход")
def ood_input():
    S["resp"] = httpx.post(f"{SERVING}/predict/iris-linear", headers={"X-Client-Id": "ood-test"},
                           json={"features": [99.0, 99.0, 99.0, 99.0]}, timeout=10)


@then("ответ помечен adversarial_suspect")
def adv_suspect():
    assert S["resp"].status_code == 200, S["resp"].text
    assert S["resp"].json().get("adversarial_suspect") is True, S["resp"].text


@then("в control-plane появляется сработка adversarial-suspect")
def adv_finding():
    r = httpx.get(f"{BASE}/api/findings", headers=tok("MLSecOps"), timeout=10)
    assert any(f["verdict"] == "adversarial-suspect" for f in r.json()["findings"]), r.text


@when("на инференс приходит malformed-запрос")
def malformed_input():
    S["resp"] = httpx.post(f"{SERVING}/predict/iris-linear", headers={"X-Client-Id": "malformed-test"},
                           json={"features": [1.0, 2.0]}, timeout=10)


@then("ответ 422 без падения сервиса")
def bad_request_alive():
    assert S["resp"].status_code == 422, S["resp"].text
    assert httpx.get(f"{SERVING}/health", timeout=10).status_code == 200
