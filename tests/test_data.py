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


# --- DATA-04 (PII-маскирование) ---
@given("DE создал датасет с PII-колонкой")
def ds_with_pii():
    r = httpx.post(f"{BASE}/api/datasets", headers=tok("DE"), json={
        "name": "customers", "sensitivity": "open", "source": "internal://crm",
        "columns": [{"name": "email", "pii": True, "sample": "alice@example.com"},
                    {"name": "amount", "pii": False, "sample": "42"}]}, timeout=10)
    assert r.status_code == 200, r.text
    S["ds_id"] = r.json()["dataset_id"]


@when("DS читает схему датасета")
def ds_reads_schema():
    S["resp"] = httpx.get(f"{BASE}/api/datasets/{S['ds_id']}/schema", headers=tok("DS"), timeout=10)


@when("MLSecOps читает схему датасета")
def sec_reads_schema():
    S["resp"] = httpx.get(f"{BASE}/api/datasets/{S['ds_id']}/schema", headers=tok("MLSecOps"), timeout=10)


def _cols():
    return {c["name"]: c for c in S["resp"].json()["columns"]}


@then("PII-значение замаскировано")
def pii_masked():
    assert _cols()["email"]["sample"] == "***", S["resp"].text


@then("не-PII значение видно")
def nonpii_visible():
    assert _cols()["amount"]["sample"] == "42", S["resp"].text


@then("PII-значение видно")
def pii_visible():
    assert _cols()["email"]["sample"] == "alice@example.com", S["resp"].text
