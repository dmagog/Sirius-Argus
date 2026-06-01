"""pytest-bdd: SUP-01 ingestion-гейт + VIS-04 триаж против живого стека.

Артефакты генерируются на лету. payload вредоносного pickle безвреден (echo) и
НИКОГДА не исполняется: gate не делает pickle.loads, а pickle.dumps лишь
сериализует инструкцию __reduce__, не вызывая её. Реального RCE нет.
"""
import os
import pickle

import httpx
from pytest_bdd import given, parsers, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
scenarios("ingest.feature")
S = {}


def tok(role):
    return {"Authorization": f"Bearer dev:{role.lower()}:{role}"}


class _Evil:
    def __reduce__(self):
        # При загрузке попросил бы os.system — но артефакт никто не загружает.
        return (os.system, ("echo sirius-demo-marker",))


def _malicious_bytes():
    return pickle.dumps(_Evil())


def _clean_bytes():
    return pickle.dumps({"model": "linear", "weights": [0.1, 0.2, 0.3]})


def _register_model():
    r = httpx.post(f"{BASE}/api/models", headers=tok("DS"),
                   json={"name": "ext", "type": "boosting", "criticality": "internal"}, timeout=10)
    assert r.status_code == 200, r.text
    return r.json()["model_id"]


@given("поднятый control-plane")
def up():
    assert httpx.get(f"{BASE}/health", timeout=10).status_code == 200, "сначала `make up` (с DEV_AUTH=1)"


@given("зарегистрирована модель для приёма")
def reg_model():
    S["model_id"] = _register_model()


@when("DS подаёт вредоносный pickle-артефакт")
def ingest_malicious():
    S["resp"] = httpx.post(f"{BASE}/api/models/{S['model_id']}/ingest", headers=tok("DS"),
                           content=_malicious_bytes(), timeout=15)


@when("DS подаёт безопасный артефакт")
def ingest_clean():
    S["resp"] = httpx.post(f"{BASE}/api/models/{S['model_id']}/ingest", headers=tok("DS"),
                           content=_clean_bytes(), timeout=15)


@then(parsers.parse("приём отклонён со статусом {code:d}"))
def rejected(code):
    assert S["resp"].status_code == code, S["resp"].text


@then(parsers.parse("приём принят со статусом {code:d}"))
def accepted(code):
    assert S["resp"].status_code == code, S["resp"].text


@then("появляется критичная сработка с вердиктом malicious")
def finding_created():
    r = httpx.get(f"{BASE}/api/findings", headers=tok("MLSecOps"), timeout=10)
    assert r.status_code == 200, r.text
    fs = [f for f in r.json()["findings"] if f["asset"] == f"model/{S['model_id']}"
          and f["verdict"] == "malicious" and f["severity"] == "critical"]
    assert fs, r.text


@then("у модели нет версий в реестре")
def no_versions():
    r = httpx.get(f"{BASE}/api/registry", headers=tok("MLSecOps"), timeout=10)
    m = next(m for m in r.json()["models"] if m["id"] == S["model_id"])
    assert m["versions"] == [], m


@then("у модели появляется версия в реестре")
def has_version():
    r = httpx.get(f"{BASE}/api/registry", headers=tok("MLSecOps"), timeout=10)
    m = next(m for m in r.json()["models"] if m["id"] == S["model_id"])
    assert len(m["versions"]) >= 1, m


# --- VIS-04 ---
@given("есть открытая сработка")
def open_finding():
    S["model_id"] = _register_model()
    httpx.post(f"{BASE}/api/models/{S['model_id']}/ingest", headers=tok("DS"),
               content=_malicious_bytes(), timeout=15)
    r = httpx.get(f"{BASE}/api/findings", headers=tok("MLSecOps"), timeout=10)
    fs = [f for f in r.json()["findings"] if f["asset"] == f"model/{S['model_id']}"]
    assert fs, r.text
    S["finding_id"] = fs[0]["id"]


@when("DS пытается перевести её в FP")
def ds_triage():
    S["resp"] = httpx.post(f"{BASE}/api/findings/{S['finding_id']}/triage", headers=tok("DS"),
                           json={"status": "FP", "reason": "x"}, timeout=10)


@when("MLSecOps переводит её в FP с обоснованием")
def sec_triage():
    S["resp"] = httpx.post(f"{BASE}/api/findings/{S['finding_id']}/triage", headers=tok("MLSecOps"),
                           json={"status": "FP", "reason": "ложное срабатывание (демо)"}, timeout=10)


@then(parsers.parse("триаж-ответ {code:d}"))
def triage_code(code):
    assert S["resp"].status_code == code, S["resp"].text


@then("статус сработки стал FP")
def status_fp():
    r = httpx.get(f"{BASE}/api/findings", headers=tok("MLSecOps"), timeout=10)
    f = next(f for f in r.json()["findings"] if f["id"] == S["finding_id"])
    assert f["status"] == "FP", f
