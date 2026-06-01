"""pytest-bdd: DATA-01 — gate на закачку датасета (карантин недоверенного источника)."""
import os

import httpx
from pytest_bdd import given, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
scenarios("data.feature")
S = {}


def tok(role):
    return {"Authorization": f"Bearer dev:{role.lower()}:{role}"}


@given("поднятый control-plane")
def up():
    assert httpx.get(f"{BASE}/health", timeout=10).status_code == 200, "сначала `make up` (с DEV_AUTH=1)"


@when("DE создаёт датасет из недоверенного источника")
def untrusted():
    S["resp"] = httpx.post(f"{BASE}/api/datasets", headers=tok("DE"),
                           json={"name": "ext", "sensitivity": "open", "source": "http://random-hub/set"}, timeout=10)


@when("DE создаёт датасет из доверенного источника")
def trusted():
    S["resp"] = httpx.post(f"{BASE}/api/datasets", headers=tok("DE"),
                           json={"name": "ext", "sensitivity": "open", "source": "internal://curated/set"}, timeout=10)


@then("датасет в статусе quarantined")
def quarantined():
    assert S["resp"].status_code == 200, S["resp"].text
    j = S["resp"].json()
    S["ds_id"] = j["dataset_id"]
    assert j["status"] == "quarantined", j


@then("датасет в статусе active")
def active():
    assert S["resp"].status_code == 200, S["resp"].text
    assert S["resp"].json()["status"] == "active", S["resp"].json()


@then("появляется сработка untrusted-source по датасету")
def untrusted_finding():
    r = httpx.get(f"{BASE}/api/findings", headers=tok("MLSecOps"), timeout=10)
    fs = [f for f in r.json()["findings"]
          if f["asset"] == f"dataset/{S['ds_id']}" and f["verdict"] == "untrusted-source"]
    assert fs, r.text
