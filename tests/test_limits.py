"""pytest-bdd: DOS-02 — защита от оверсайз-загрузок (resource-exhaustion).

Тело больше MAX_UPLOAD_BYTES режется на app-уровне (по Content-Length, без чтения в память)
→ 413 + Finding(oversized-upload) + аудит. На периметре дополнительно жёсткий потолок Caddy.
"""
import os

import httpx
from pytest_bdd import given, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
scenarios("limits.feature")
S = {}


def tok(role):
    return {"Authorization": f"Bearer dev:{role.lower()}:{role}"}


@given("поднятый control-plane")
def up():
    assert httpx.get(f"{BASE}/health", timeout=10).status_code == 200, "сначала `make up` (с DEV_AUTH=1)"


@when("DS подаёт артефакт больше лимита")
def oversized():
    mid = httpx.post(f"{BASE}/api/models", headers=tok("DS"),
                     json={"name": "huge", "criticality": "internal"}, timeout=10).json()["model_id"]
    big = b"\x00" * (26 * 1024 * 1024)  # 26 МиБ > лимита 25 МиБ
    S["resp"] = httpx.post(f"{BASE}/api/models/{mid}/ingest", headers=tok("DS"), content=big, timeout=30)


@then("загрузка отклонена со статусом 413")
def rejected_413():
    assert S["resp"].status_code == 413, S["resp"].status_code


@then("появляется сработка oversized-upload")
def oversized_finding():
    r = httpx.get(f"{BASE}/api/findings", headers=tok("MLSecOps"), timeout=10)
    assert any(f["verdict"] == "oversized-upload" for f in r.json()["findings"]), r.text
