"""pytest-bdd: доказательный аппрув-гейт — review-бандл даёт аппруверу доказательства (VIS-03+)."""
import os
import struct

import httpx
from pytest_bdd import given, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
scenarios("approval_gate.feature")
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


@when("MLSecOps отклоняет критичную версию с обоснованием")
def reject_critical_version():
    # критичная версия с полным гейтом (модель-карта + lineage + подпись) — единственным
    # незакрытым условием остаётся решение аппрув-гейта, чтобы изолировать поведение reject
    dv = httpx.post(f"{BASE}/api/datasets", headers=tok("DE"),
                    json={"name": "reject-data", "source": "internal://curated/reject"}, timeout=60).json()
    mid = httpx.post(f"{BASE}/api/models", headers=tok("DS"),
                     json={"name": "reject-demo", "criticality": "financial"}, timeout=60).json()["model_id"]
    ver = httpx.post(f"{BASE}/api/models/{mid}/versions", headers=tok("DS"),
                     json={"dataset_version_id": dv["dataset_version_id"], "code_commit": "rj01",
                           "env_lock": "req.lock", "intended_use": "демо отклонения",
                           "limitations": "только для теста"}, timeout=60).json()["version"]
    httpx.post(f"{BASE}/api/models/{mid}/versions/{ver}/sign", headers=tok("MLSecOps"), timeout=60)
    rj = httpx.post(f"{BASE}/api/models/{mid}/versions/{ver}/reject", headers=tok("MLSecOps"),
                    json={"reason": "метрики просели на холдауте"}, timeout=60)
    assert rj.status_code == 200, rj.text
    S.update(mid=mid, ver=ver)


@then("промоушен этой версии блокируется как отклонённый")
def promote_blocked_rejected():
    r = httpx.post(f"{BASE}/api/models/{S['mid']}/versions/{S['ver']}/promote",
                   headers=tok("MLSecOps"), timeout=60)
    assert r.status_code == 422, r.text
    assert "reject" in (r.json().get("detail", "").lower())


@then("повторный аппрув другим MLSecOps снимает блок и версия уходит в прод")
def reapprove_unblocks():
    # аппрув ОТ ДРУГОГО MLSecOps (reviewer) поверх отклонения; промоутит третий (mlsecops) —
    # separation of duties соблюдена, версия проходит гейт и уходит в прод
    a = httpx.post(f"{BASE}/api/models/{S['mid']}/versions/{S['ver']}/approve",
                   headers={"Authorization": "Bearer dev:reviewer:MLSecOps"},
                   json={"reason": "переобучили, метрики восстановлены"}, timeout=60)
    assert a.status_code == 200, a.text
    p = httpx.post(f"{BASE}/api/models/{S['mid']}/versions/{S['ver']}/promote",
                   headers=tok("MLSecOps"), timeout=60)
    assert p.status_code == 200, p.text
    assert p.json().get("stage") == "prod"
