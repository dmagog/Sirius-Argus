"""pytest-bdd: SUP-01 ingestion-гейт + VIS-04 триаж против живого стека.

Артефакты генерируются на лету. payload вредоносного pickle безвреден (echo) и
НИКОГДА не исполняется: gate не делает pickle.loads, а pickle.dumps лишь
сериализует инструкцию __reduce__, не вызывая её. Реального RCE нет.
"""
import json
import os
import pickle
import struct

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


class _Benign:
    def __init__(self):
        self.w = [1, 2, 3]


def _benign_code_bytes():
    # код-несущий, но безопасный pickle (ссылка на безобидный класс) — для VIS-02
    return pickle.dumps(_Benign())


def _register_model(criticality="internal"):
    r = httpx.post(f"{BASE}/api/models", headers=tok("DS"),
                   json={"name": "ext", "type": "boosting", "criticality": criticality}, timeout=60)
    assert r.status_code == 200, r.text
    return r.json()["model_id"]


def _safetensors_bytes():
    # минимальный валидный safetensors: 8-байтный LE-префикс длины + JSON-заголовок
    header = json.dumps({"__metadata__": {"producer": "sirius-demo"}}).encode()
    return struct.pack("<Q", len(header)) + header


@given("поднятый control-plane")
def up():
    assert httpx.get(f"{BASE}/health", timeout=60).status_code == 200, "сначала `make up` (с DEV_AUTH=1)"


@given("зарегистрирована модель для приёма")
def reg_model():
    S["model_id"] = _register_model()


@when("DS подаёт вредоносный pickle-артефакт")
def ingest_malicious():
    S["resp"] = httpx.post(f"{BASE}/api/models/{S['model_id']}/ingest", headers=tok("DS"),
                           content=_malicious_bytes(), timeout=60)


@when("DS подаёт безопасный артефакт")
def ingest_clean():
    S["resp"] = httpx.post(f"{BASE}/api/models/{S['model_id']}/ingest", headers=tok("DS"),
                           content=_clean_bytes(), timeout=60)


@then(parsers.parse("приём отклонён со статусом {code:d}"))
def rejected(code):
    assert S["resp"].status_code == code, S["resp"].text


@then(parsers.parse("приём принят со статусом {code:d}"))
def accepted(code):
    assert S["resp"].status_code == code, S["resp"].text


@then("появляется критичная сработка с вердиктом malicious")
def finding_created():
    r = httpx.get(f"{BASE}/api/findings", headers=tok("MLSecOps"), timeout=60)
    assert r.status_code == 200, r.text
    fs = [f for f in r.json()["findings"] if f["asset"] == f"model/{S['model_id']}"
          and f["verdict"] == "malicious" and f["severity"] == "critical"]
    assert fs, r.text


@then("у модели нет версий в реестре")
def no_versions():
    r = httpx.get(f"{BASE}/api/registry", headers=tok("MLSecOps"), timeout=60)
    m = next(m for m in r.json()["models"] if m["id"] == S["model_id"])
    assert m["versions"] == [], m


@then("у модели появляется версия в реестре")
def has_version():
    r = httpx.get(f"{BASE}/api/registry", headers=tok("MLSecOps"), timeout=60)
    m = next(m for m in r.json()["models"] if m["id"] == S["model_id"])
    assert len(m["versions"]) >= 1, m


# --- VIS-04 ---
@given("есть открытая сработка")
def open_finding():
    S["model_id"] = _register_model()
    httpx.post(f"{BASE}/api/models/{S['model_id']}/ingest", headers=tok("DS"),
               content=_malicious_bytes(), timeout=60)
    r = httpx.get(f"{BASE}/api/findings", headers=tok("MLSecOps"), timeout=60)
    fs = [f for f in r.json()["findings"] if f["asset"] == f"model/{S['model_id']}"]
    assert fs, r.text
    S["finding_id"] = fs[0]["id"]


@when("DS пытается перевести её в FP")
def ds_triage():
    S["resp"] = httpx.post(f"{BASE}/api/findings/{S['finding_id']}/triage", headers=tok("DS"),
                           json={"status": "FP", "reason": "x"}, timeout=60)


@when("MLSecOps переводит её в FP с обоснованием")
def sec_triage():
    S["resp"] = httpx.post(f"{BASE}/api/findings/{S['finding_id']}/triage", headers=tok("MLSecOps"),
                           json={"status": "FP", "reason": "ложное срабатывание (демо)"}, timeout=60)


@then(parsers.parse("триаж-ответ {code:d}"))
def triage_code(code):
    assert S["resp"].status_code == code, S["resp"].text


@then("статус сработки стал FP")
def status_fp():
    r = httpx.get(f"{BASE}/api/findings", headers=tok("MLSecOps"), timeout=60)
    f = next(f for f in r.json()["findings"] if f["id"] == S["finding_id"])
    assert f["status"] == "FP", f


# --- SUP-07 (политика форматов по критичности) ---
@given("зарегистрирована критичная модель для приёма")
def reg_crit_model():
    S["model_id"] = _register_model("financial")


@when("DS подаёт чистый pickle-артефакт")
def ingest_clean_pickle():
    S["resp"] = httpx.post(f"{BASE}/api/models/{S['model_id']}/ingest", headers=tok("DS"),
                           content=_clean_bytes(), timeout=60)


@when("DS подаёт артефакт в формате safetensors")
def ingest_safetensors():
    S["resp"] = httpx.post(f"{BASE}/api/models/{S['model_id']}/ingest", headers=tok("DS"),
                           content=_safetensors_bytes(), timeout=60)


@when("DS подаёт артефакт-архив (zip)")
def ingest_archive():
    # архив = контейнер с произвольными файлами; принимаем только одиночный проверенный артефакт
    S["resp"] = httpx.post(f"{BASE}/api/models/{S['model_id']}/ingest", headers=tok("DS"),
                           content=b"PK\x03\x04" + b"\x00" * 40, timeout=60)


@then("появляется сработка о небезопасном формате")
def unsafe_format_finding():
    r = httpx.get(f"{BASE}/api/findings", headers=tok("MLSecOps"), timeout=60)
    fs = [f for f in r.json()["findings"]
          if f["asset"] == f"model/{S['model_id']}" and f["verdict"] == "unsafe-format"]
    assert fs, r.text


# --- VIS-02 (расхождение вердиктов сканеров) ---
@when("DS подаёт артефакт, подозрительный для второго сканера")
def ingest_benign_code():
    S["resp"] = httpx.post(f"{BASE}/api/models/{S['model_id']}/ingest", headers=tok("DS"),
                           content=_benign_code_bytes(), timeout=60)


@then("есть сработка suspicious от эвристического сканера")
def suspicious_finding():
    r = httpx.get(f"{BASE}/api/findings", headers=tok("MLSecOps"), timeout=60)
    fs = [f for f in r.json()["findings"]
          if f["asset"] == f"model/{S['model_id']}" and f["verdict"] == "suspicious"
          and f["tool"] == "sirius-heuristic-scan"]
    assert fs, r.text
    S["finding_id"] = fs[0]["id"]


# --- TOCTOU-01 / SUP-05 (целостность артефакта при загрузке) ---
@when("DS подаёт безопасный артефакт и проверяет целостность")
def ingest_and_verify():
    art = _clean_bytes()
    r = httpx.post(f"{BASE}/api/models/{S['model_id']}/ingest", headers=tok("DS"), content=art, timeout=60)
    assert r.status_code == 200, r.text
    ver = r.json()["version"]
    base = f"{BASE}/api/models/{S['model_id']}/versions/{ver}/verify-artifact"
    S["verify_ok"] = httpx.post(base, headers=tok("MLSecOps"), content=art, timeout=60).status_code
    S["verify_tampered"] = httpx.post(base, headers=tok("MLSecOps"), content=art + b"TAMPER", timeout=60).status_code


@then("целостность подтверждается для исходного и нарушается для подменённого")
def integrity_checks():
    assert S["verify_ok"] == 200, S
    assert S["verify_tampered"] == 409, S
