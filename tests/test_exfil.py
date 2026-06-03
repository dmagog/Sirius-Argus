"""pytest-bdd: EXF-01 — детект инсайдерской массовой выгрузки моделей."""
import os
import subprocess

import httpx
from pytest_bdd import given, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
scenarios("exfil.feature")
S = {}


def tok(role):
    return {"Authorization": f"Bearer dev:{role.lower()}:{role}"}


def _redis_pw():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        for line in open(os.path.join(repo, ".env")):
            if line.startswith("REDIS_PASSWORD="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return "sirius-redis"


def _redis(*args):
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = subprocess.run(["docker", "compose", "exec", "-T", "redis", "redis-cli", "-a", _redis_pw(), *args],
                         cwd=repo, capture_output=True, text=True, timeout=20)
    return out.returncode, out.stdout.strip()


@given("поднятый control-plane")
def up():
    assert httpx.get(f"{BASE}/health", timeout=10).status_code == 200, "сначала `make up` (с DEV_AUTH=1)"


@when("актор выгружает модель аномально много раз")
def bulk_export():
    mid = httpx.post(f"{BASE}/api/models", headers=tok("DS"),
                     json={"name": "exportable", "type": "boosting", "criticality": "internal"}, timeout=10).json()["model_id"]
    last = None
    for _ in range(20):
        last = httpx.get(f"{BASE}/api/models/{mid}/export", headers=tok("DS"), timeout=10)
    S["last"] = last


@then("выгрузка троттлится со статусом 429")
def throttled():
    assert S["last"].status_code == 429, S["last"].text


@then("появляется сработка bulk-exfiltration по актору")
def exfil_finding():
    r = httpx.get(f"{BASE}/api/findings", headers=tok("MLSecOps"), timeout=10)
    assert any(f["verdict"] == "bulk-exfiltration" and f["asset"].startswith("actor/")
               for f in r.json()["findings"]), r.text


@then("счётчик выгрузок ведётся в общем Redis, а не в памяти воркера")
def counter_in_redis():
    # доказываем, что лимит держится в shared-store: ключ окна актора есть в Redis с хитами.
    # Значит размазать запросы по нескольким воркерам и обойти лимит нельзя (находка из ревью).
    rc, out = _redis("ZCARD", "exfil:hits:ds")
    assert rc == 0 and out.isdigit() and int(out) > 0, f"ожидали счётчик окна в Redis, получили: {out!r}"
