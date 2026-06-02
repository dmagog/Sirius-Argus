"""pytest-bdd: сервинг трио моделей + рантайм-защиты (RT-01/02/05, MON-01, RT-03/04/06)."""
import os
import subprocess

import httpx
from pytest_bdd import given, scenarios, then, when

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # корень репо (docker-compose.yml)

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


@when("на сервинг идёт поток входов со смещённым распределением")
def drift_stream():
    # > _DRIFT_WINDOW(15) запросов со сдвинутым распределением (далеко от обучающего μ) —
    # окно на (модель,клиент) заполняется → популяционный дрейф (MON-01), не одиночный OOD.
    h = {"X-Client-Id": "drift-test"}
    last = None
    for _ in range(18):
        last = httpx.post(f"{SERVING}/predict/iris-linear", headers=h,
                          json={"features": [12.0, 9.0, 10.0, 8.0]}, timeout=10)
    S["resp"] = last


@then("в control-plane появляется сработка drift")
def drift_finding():
    assert S["resp"].status_code == 200, S["resp"].text
    r = httpx.get(f"{BASE}/api/findings", headers=tok("MLSecOps"), timeout=10)
    assert any(f["verdict"] == "drift" for f in r.json()["findings"]), r.text


@when("клиент запрашивает предсказание")
def one_predict():
    S["resp"] = httpx.post(f"{SERVING}/predict/iris-linear", headers={"X-Client-Id": "outred-test"},
                           json={"features": [5.1, 3.5, 1.4, 0.2]}, timeout=10)


@then("ответ содержит метку класса, но не вероятности/скоры")
def no_scores():
    # RT-03/04: output reduction — наружу только категория, без confidence (membership/inversion).
    j = S["resp"].json()
    assert S["resp"].status_code == 200 and "label" in j, j
    banned = {"proba", "probabilities", "probability", "confidence", "score", "scores", "logits", "logit"}
    assert not (set(k.lower() for k in j) & banned), j


@when("тенант превышает свой бюджет запросов")
def dow_burst():
    # уникальный client-id → burst RT-01 (50) не срабатывает; X-Tenant-Id → действует cost-квота DOW-01 (30)
    h = {"X-Client-Id": "dow-client", "X-Tenant-Id": "acme-pay"}
    last = None
    for _ in range(33):
        last = httpx.post(f"{SERVING}/predict/iris-linear", headers=h, json={"features": [5.1, 3.5, 1.4, 0.2]}, timeout=10)
    S["resp"] = last


@then("сервинг отвечает 429 denial-of-wallet")
def dow_throttled():
    assert S["resp"].status_code == 429, S["resp"].text
    assert "denial-of-wallet" in S["resp"].text.lower(), S["resp"].text


@then("в control-plane появляется сработка denial-of-wallet")
def dow_finding():
    r = httpx.get(f"{BASE}/api/findings", headers=tok("MLSecOps"), timeout=10)
    assert any(f["verdict"] == "denial-of-wallet" for f in r.json()["findings"]), r.text


@then("из сервинга недоступны MLflow и MinIO, но доступен control-plane")
def lateral_blocked():
    # RT-06: serving в изолированном тире runtime — DNS/маршрут к хранилищам отрезан,
    # достижим только control-plane. Проверяем изнутри контейнера сервинга.
    code = ("import socket\n"
            "r={}\n"
            "for n,h,p in (('mlflow','mlflow',5000),('minio','minio',9000),('cp','control-plane',8000)):\n"
            "    try:\n"
            "        s=socket.create_connection((h,p),2); s.close(); r[n]=True\n"
            "    except Exception: r[n]=False\n"
            "print(r)")
    res = subprocess.run(["docker", "compose", "exec", "-T", "serving", "python", "-c", code],
                         cwd=REPO, capture_output=True, text=True, timeout=40)
    out = res.stdout + res.stderr
    assert "'mlflow': False" in out and "'minio': False" in out, out
    assert "'cp': True" in out, out
