"""pytest-bdd: evidence-based HITL — review-бандл даёт аппруверу доказательства (VIS-03+)."""
import os
import struct

import httpx
from pytest_bdd import given, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
scenarios("hitl.feature")
S = {}


def tok(role):
    return {"Authorization": f"Bearer dev:{role.lower()}:{role}"}


def _safetensors():
    hdr = b'{"__metadata__": {"producer": "sirius"}}'
    return struct.pack("<Q", len(hdr)) + hdr


@given("поднятый control-plane")
def up():
    assert httpx.get(f"{BASE}/health", timeout=60).status_code == 200, "сначала `make up` (с DEV_AUTH=1)"


@when("DS подаёт чистый артефакт и запрашивается review-бандл версии")
def ingest_and_review():
    mid = httpx.post(f"{BASE}/api/models", headers=tok("DS"),
                     json={"name": "review-demo", "criticality": "internal"}, timeout=60).json()["model_id"]
    r = httpx.post(f"{BASE}/api/models/{mid}/ingest", headers=tok("DS"), content=_safetensors(), timeout=60)
    ver = r.json()["version"]
    S["resp"] = httpx.get(f"{BASE}/api/models/{mid}/versions/{ver}/review", headers=tok("MLSecOps"), timeout=60)


@then("в бандле есть модель-карта, lineage, статус подписи и сработки")
def bundle_has_evidence():
    assert S["resp"].status_code == 200, S["resp"].text
    j = S["resp"].json()
    for k in ("model_card", "lineage", "signature", "findings", "open_critical", "approvals"):
        assert k in j, j
    assert "complete" in j["model_card"] and "reproducible" in j["lineage"] and "signed" in j["signature"]
