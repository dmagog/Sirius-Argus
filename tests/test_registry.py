"""pytest-bdd: реестр + RBAC против живого стека (роли через dev-токены, DEV_AUTH=1)."""
import os
import subprocess

import httpx
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
scenarios("registry.feature")

S = {}


def tok(role):
    return {"Authorization": f"Bearer dev:{role.lower()}:{role}"}


def _dataset(sensitivity):
    r = httpx.post(f"{BASE}/api/datasets", headers=tok("DE"),
                   json={"name": "d", "sensitivity": sensitivity, "source": "demo"}, timeout=10)
    assert r.status_code == 200, r.text
    return r.json()


def _register_model_version(with_lineage):
    dv = _dataset("open")["dataset_version_id"] if with_lineage else None
    m = httpx.post(f"{BASE}/api/models", headers=tok("DS"),
                   json={"name": "m", "type": "boosting", "criticality": "financial"}, timeout=10).json()
    body = {"dataset_version_id": dv, "code_commit": "abc123", "env_lock": "req.lock"} if with_lineage else {}
    v = httpx.post(f"{BASE}/api/models/{m['model_id']}/versions", headers=tok("DS"), json=body, timeout=10).json()
    S.update(model_id=m["model_id"], ver=v["version"], dv=dv)


@given("поднятый control-plane")
def up():
    assert httpx.get(f"{BASE}/health", timeout=10).status_code == 200, "сначала `make up` (с DEV_AUTH=1)"


@given("зарегистрирована модель с воспроизводимой версией")
def reproducible():
    _register_model_version(True)


@given("зарегистрирована модель с невоспроизводимой версией")
def non_reproducible():
    _register_model_version(False)


@given("DE создал секретный датасет")
def secret_dataset():
    S["ds_id"] = _dataset("secret")["dataset_id"]


@when("DS пытается промоутить версию")
def ds_promote():
    S["resp"] = httpx.post(f"{BASE}/api/models/{S['model_id']}/versions/{S['ver']}/promote", headers=tok("DS"), timeout=10)


@when("MLSecOps пытается промоутить версию")
def sec_promote():
    S["resp"] = httpx.post(f"{BASE}/api/models/{S['model_id']}/versions/{S['ver']}/promote", headers=tok("MLSecOps"), timeout=10)


@when("DS читает секретный датасет")
def ds_read_secret():
    S["resp"] = httpx.get(f"{BASE}/api/datasets/{S['ds_id']}", headers=tok("DS"), timeout=10)


@when("Product читает секретный датасет")
def product_read_secret():
    S["resp"] = httpx.get(f"{BASE}/api/datasets/{S['ds_id']}", headers=tok("Product"), timeout=10)


@then(parsers.parse("ответ {code:d}"))
def check(code):
    assert S["resp"].status_code == code, S["resp"].text


@then("blast-radius по датасету показывает модель")
def impact_shows():
    r = httpx.get(f"{BASE}/api/impact", params={"dataset_version_id": S["dv"]}, headers=tok("MLSecOps"), timeout=10)
    assert r.status_code == 200 and len(r.json()["affected"]) >= 1, r.text


@given("реестр на MLflow доступен")
def mlflow_up():
    h = httpx.get(f"{BASE}/health", timeout=10).json()
    if not h.get("mlflow", {}).get("connected"):
        pytest.skip("MLflow backend не поднят")


@then("версия видна в MLflow-реестре через control-plane")
def version_in_mlflow():
    r = httpx.get(f"{BASE}/api/models/{S['model_id']}/backend", headers=tok("MLSecOps"), timeout=10)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["backend"] == "mlflow" and j["present"] is True, j
    assert any(str(v["cp_version"]) == str(S["ver"]) for v in j["versions"]), j


@then("прямой доступ к MLflow снаружи закрыт")
def mlflow_not_exposed():
    # Истинный инвариант zero-trust: docker не публикует порт MLflow на хост.
    # (Прямая проба localhost:5000 ненадёжна — на macOS порт занимает AirPlay.)
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = subprocess.run(["docker", "compose", "port", "mlflow", "5000"],
                         cwd=repo, capture_output=True, text=True, timeout=15)
    assert out.stdout.strip() == "", f"MLflow порт опубликован наружу: {out.stdout!r}"
