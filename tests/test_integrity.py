"""pytest-bdd: MON-04 — tamper-evidence аудита (hash-chain).

Подменяем запись прямо в БД (psql) и проверяем, что /health.audit_chain_ok ловит
подмену; затем откатываем — цепочка восстанавливается. Без изменений control-plane.
"""
import os
import subprocess

import httpx
from pytest_bdd import given, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
scenarios("integrity.feature")
S = {}


def _psql(sql):
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = subprocess.run(["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "sirius", "-d", "sirius", "-tAc", sql],
                         cwd=repo, capture_output=True, text=True, timeout=20)
    return out.stdout.strip()


def _chain_ok():
    return httpx.get(f"{BASE}/health", timeout=10).json()["audit_chain_ok"]


@given("поднятый control-plane с целым аудитом")
def intact_audit():
    # порождаем хотя бы одно событие аудита и проверяем, что цепочка цела
    httpx.get(f"{BASE}/api/whoami", headers={"Authorization": "Bearer dev:ds:DS"}, timeout=10)
    assert _chain_ok() is True, "цепочка нарушена ещё до подмены"
    S["rid"] = _psql("SELECT max(id) FROM audit_events")
    assert S["rid"], "нет записей аудита"


@when("кто-то подменяет запись в журнале аудита")
def tamper():
    _psql(f"UPDATE audit_events SET was_authorized = NOT was_authorized WHERE id = {S['rid']}")
    S["after_tamper"] = _chain_ok()
    _psql(f"UPDATE audit_events SET was_authorized = NOT was_authorized WHERE id = {S['rid']}")  # откат
    S["after_restore"] = _chain_ok()


@then("проверка целостности падает")
def broken():
    assert S["after_tamper"] is False, "подмена не обнаружена hash-chain'ом"


@then("после отката подмены целостность восстанавливается")
def restored():
    assert S["after_restore"] is True, "цепочка не восстановилась после отката"
