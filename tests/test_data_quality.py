"""pytest-bdd: DATA-02/03/05 + FB-01 — гейт качества/целостности данных (anti-poisoning)."""
import os

import httpx
from pytest_bdd import given, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
scenarios("data_quality.feature")
S = {}


def tok(role):
    return {"Authorization": f"Bearer dev:{role.lower()}:{role}"}


def _scan(payload):
    return httpx.post(f"{BASE}/api/scan/dataset", headers=tok("DE"), json=payload, timeout=10)


def _has(verdict):
    r = httpx.get(f"{BASE}/api/findings", headers=tok("MLSecOps"), timeout=10)
    return any(f["verdict"] == verdict for f in r.json()["findings"]), r


@given("поднятый control-plane")
def up():
    assert httpx.get(f"{BASE}/health", timeout=10).status_code == 200, "сначала `make up` (с DEV_AUTH=1)"


@when("DE сканирует набор с подменёнными метками")
def scan_labelflip():
    # распределение меток уехало от baseline (fraud 0.05→0.9) — признак подмены
    S["resp"] = _scan({"labels": ["fraud"] * 9 + ["legit"], "baseline_dist": {"fraud": 0.05, "legit": 0.95}})


@when("DE сканирует UGC-сэмплы с невидимым триггером")
def scan_backdoor():
    S["resp"] = _scan({"samples": ["обычный отзыв", "отличный товар​​купите сейчас"]})


@when("DE сканирует статистики с расхождением train и serve")
def scan_skew():
    S["resp"] = _scan({"train_stats": {"amount": 100.0, "age": 35.0},
                       "serve_stats": {"amount": 900.0, "age": 36.0}})


@when("DE сканирует фидбек без доверенного провенанса")
def scan_feedback():
    S["resp"] = _scan({"feedback": [{"provenance": "user-submitted"}, {"provenance": "verified"}]})


@then("скан данных небезопасен")
def data_unsafe():
    assert S["resp"].status_code == 200, S["resp"].text
    assert S["resp"].json()["clean"] is False, S["resp"].text


@then("создаётся сработка label-flip")
def f_labelflip():
    ok, r = _has("label-flip")
    assert ok, r.text


@then("создаётся сработка backdoor-trigger")
def f_backdoor():
    ok, r = _has("backdoor-trigger")
    assert ok, r.text


@then("создаётся сработка train-serve-skew")
def f_skew():
    ok, r = _has("train-serve-skew")
    assert ok, r.text


@then("создаётся сработка feedback-poisoning")
def f_feedback():
    ok, r = _has("feedback-poisoning")
    assert ok, r.text
