"""pytest-bdd: EVT-01 — события идут в шину и в аудит. Скип, если Redis не поднят."""
import os

import httpx
import pytest
from pytest_bdd import given, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
scenarios("bus.feature")

S = {}


@given("поднятая шина событий")
def bus_up():
    h = httpx.get(f"{BASE}/health", timeout=10).json()
    if not h.get("bus", {}).get("connected"):
        pytest.skip("шина (Redis) не поднята")
    S["events0"] = h["bus"]["events"]


@when("MLSecOps вызывает whoami")
def call():
    r = httpx.get(f"{BASE}/api/whoami", headers={"Authorization": "Bearer dev:mlsecops:MLSecOps"}, timeout=10)
    assert r.status_code == 200, r.text


@then("число событий в шине выросло")
def grew():
    h = httpx.get(f"{BASE}/health", timeout=10).json()
    assert h["bus"]["events"] > S["events0"]


@then("действие есть в аудит-таймлайне")
def in_audit():
    assert "api.whoami" in httpx.get(f"{BASE}/ui/audit", timeout=10).text
