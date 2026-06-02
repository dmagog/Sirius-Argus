"""pytest-bdd: DOS-01 — глобальный load-shedding при распределённом флуде."""
import concurrent.futures
import os

import httpx
from pytest_bdd import given, scenarios, then, when

SERVING = os.environ.get("SERVING_URL", "http://localhost:8001")
scenarios("dos.feature")
S = {}


@given("поднятый сервинг")
def up():
    assert httpx.get(f"{SERVING}/health", timeout=10).status_code == 200, "сначала `make up`"


@when("по сервингу бьёт распределённый флуд")
def flood():
    def one(i):
        try:  # уникальный client-id у каждого → это не per-client extraction (RT-01), а глобальный флуд
            return httpx.post(f"{SERVING}/predict/iris-linear", headers={"X-Client-Id": f"ddos-{i}"},
                              json={"features": [5.1, 3.5, 1.4, 0.2]}, timeout=10).status_code
        except Exception:
            return 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=40) as ex:
        S["codes"] = list(ex.map(one, range(250)))


@then("часть запросов отброшена со статусом 503")
def shed():
    assert S["codes"].count(503) > 0, f"нет 503 (load-shedding не сработал): {sorted(set(S['codes']))}"


@then("сервинг остаётся живым")
def alive():
    assert httpx.get(f"{SERVING}/health", timeout=10).status_code == 200
