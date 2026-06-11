"""Обёртка над MLflow Model Registry (ADR-0001).

MLflow поднят только во внутренней сети — порт наружу не публикуется. Реестр
моделей/версий хранится в MLflow; control-plane — единственная дверь к нему и
владеет RBAC/аудитом. Запись идёт write-through и fail-soft: если MLflow
недоступен, control-plane не падает, версия помечается как не синхронизированная
(backend_synced=False), а состояние backend видно в /health.
"""
import logging
import os
import re

import requests

logger = logging.getLogger("sirius")

MLFLOW = os.environ.get("MLFLOW_TRACKING_URI", "").rstrip("/")
# basic-auth к MLflow-реестру: control-plane — единственная дверь не только по сети, но и по
# аутентификации (рандомный контейнер во internal-сети не пишет в реестр без логина).
_USER = os.environ.get("MLFLOW_TRACKING_USERNAME", "")
_PASS = os.environ.get("MLFLOW_TRACKING_PASSWORD", "")
_AUTH = (_USER, _PASS) if _USER else None
_HEALTH_TIMEOUT = 2
_TIMEOUT = 5


class RegistryError(RuntimeError):
    pass


def _api(path):
    return f"{MLFLOW}/api/2.0/mlflow{path}"


def configured():
    return bool(MLFLOW)


def connected():
    if not MLFLOW:
        return False
    try:
        return requests.get(f"{MLFLOW}/health", auth=_AUTH, timeout=_HEALTH_TIMEOUT).status_code == 200
    except requests.RequestException:
        return False


def model_name(model_id, name):
    """Детерминированное имя в MLflow: sirius-<id>-<sanitized>."""
    safe = re.sub(r"[^A-Za-z0-9_.\-]", "_", name)[:64]
    return f"sirius-{model_id}-{safe}"


def _tags(d):
    return [{"key": str(k), "value": str(v)} for k, v in (d or {}).items() if v not in (None, "")]


def ensure_registered_model(name, tags=None):
    """Идемпотентно: создаёт registered model; «уже существует» — это ок."""
    try:
        r = requests.post(_api("/registered-models/create"), auth=_AUTH,
                          json={"name": name, "tags": _tags(tags)}, timeout=_TIMEOUT)
    except requests.RequestException as e:
        raise RegistryError(str(e))
    if r.status_code == 200 or "RESOURCE_ALREADY_EXISTS" in r.text:
        return
    raise RegistryError(f"create registered-model: {r.status_code} {r.text}")


def create_model_version(name, source, tags=None):
    try:
        r = requests.post(_api("/model-versions/create"), auth=_AUTH,
                          json={"name": name, "source": source, "tags": _tags(tags)}, timeout=_TIMEOUT)
    except requests.RequestException as e:
        raise RegistryError(str(e))
    if r.status_code != 200:
        raise RegistryError(f"create model-version: {r.status_code} {r.text}")
    return r.json()["model_version"]["version"]


def get_registered_model(name):
    """Запись MLflow (имя + версии с тегами) или None, если нет/недоступно."""
    try:
        r = requests.get(_api("/registered-models/get"), auth=_AUTH, params={"name": name}, timeout=_TIMEOUT)
        if r.status_code != 200:
            return None
        rm = r.json().get("registered_model", {})
        s = requests.get(_api("/model-versions/search"), auth=_AUTH, params={"filter": f"name='{name}'"}, timeout=_TIMEOUT)
        versions = s.json().get("model_versions", []) if s.status_code == 200 else rm.get("latest_versions", [])
        return {"name": name, "versions": versions}
    except requests.RequestException:
        return None


def find_version_by_cp(name, cp_version):
    """MLflow-версия, помеченная нашим cp_version (наши номера могут расходиться с MLflow)."""
    rm = get_registered_model(name)
    if not rm:
        return None
    for v in rm["versions"]:
        tags = {t["key"]: t["value"] for t in v.get("tags", [])}
        if tags.get("cp_version") == str(cp_version):
            return v["version"]
    return None


def set_version_tag(name, version, key, value):
    try:
        r = requests.post(_api("/model-versions/set-tag"), auth=_AUTH,
                          json={"name": name, "version": str(version), "key": key, "value": str(value)}, timeout=_TIMEOUT)
    except requests.RequestException as e:
        raise RegistryError(str(e))
    if r.status_code != 200:
        raise RegistryError(f"set-tag: {r.status_code} {r.text}")
