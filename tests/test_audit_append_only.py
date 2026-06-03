"""pytest-bdd: LOG-02 — append-only журнал аудита (prevent).

Дополняет MON-04 (детект): запись аудита нельзя изменить или удалить обычным DML —
БД-триггер отбивает UPDATE и DELETE даже под ролью владельца, которой пользуется
control-plane. Переписать hash-chain через скомпрометированный control-plane по
DML-пути нельзя. Чтобы вообще тронуть запись, нужен привилегированный DDL (отключить
триггер) — а это уже отдельное, заметное действие (см. MON-04 в test_integrity).
"""
import os
import subprocess

import httpx
from pytest_bdd import given, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
scenarios("audit_append_only.feature")
S = {}


def _psql(sql):
    """psql с ON_ERROR_STOP: returncode != 0, если БД отбила запрос (нужно для проверки триггера)."""
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "sirius", "-d", "sirius",
         "-v", "ON_ERROR_STOP=1", "-tAc", sql],
        cwd=repo, capture_output=True, text=True, timeout=20)
    return out.returncode, (out.stdout + out.stderr).strip()


def _chain_ok():
    return httpx.get(f"{BASE}/health", timeout=10).json()["audit_chain_ok"]


@given("поднятый control-plane с целым аудитом")
def intact_audit():
    httpx.get(f"{BASE}/api/whoami", headers={"Authorization": "Bearer dev:ds:DS"}, timeout=10)
    assert _chain_ok() is True, "цепочка нарушена ещё до попытки подмены"
    rc, rid = _psql("SELECT max(id) FROM audit_events")
    assert rc == 0 and rid, "нет записей аудита"
    S["rid"] = rid


@when("кто-то пытается изменить или удалить запись аудита напрямую в БД")
def attempt_mutation():
    # ровно тот путь, которым скомпрометированный control-plane переписывал бы цепочку — обычный DML
    S["upd_rc"], S["upd_out"] = _psql(f"UPDATE audit_events SET actor='attacker' WHERE id={S['rid']}")
    S["del_rc"], S["del_out"] = _psql(f"DELETE FROM audit_events WHERE id={S['rid']}")


@then("БД отклоняет изменение и удаление как append-only")
def rejected():
    assert S["upd_rc"] != 0, f"UPDATE аудита не отклонён: {S['upd_out']}"
    assert S["del_rc"] != 0, f"DELETE аудита не отклонён: {S['del_out']}"
    assert "append-only" in (S["upd_out"] + S["del_out"]).lower(), "ожидали ошибку append-only от триггера"


@then("журнал аудита остаётся целым")
def still_intact():
    rc, actor = _psql(f"SELECT actor FROM audit_events WHERE id={S['rid']}")
    assert rc == 0 and actor != "attacker", "запись всё-таки изменена"
    assert _chain_ok() is True, "цепочка нарушена после отбитой попытки"
