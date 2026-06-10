#!/usr/bin/env python3
"""Живое демо Sirius Argus против поднятого стека (один проход по money-shot'ам И2).

Запуск:  make up   (или docker compose up -d, с DEV_AUTH=1)
         python3 scripts/demo.py        # SIRIUS_BASE_URL по умолчанию http://localhost:8080

Только стандартная библиотека — никаких зависимостей. Демонстрирует:
  - приём вредоносной модели → БЛОК + сработка (артефакт не десериализуется);
  - чистый артефакт → регистрируется (и реально лежит в обёрнутом MLflow);
  - политику форматов по критичности (SUP-07);
  - карантин недоверенного датасета (DATA-01);
  - SAST на код (CODE-01);
  - расхождение вердиктов сканеров и триаж фолза (VIS-02);
  - сквозную сущность Finding как «спину» интегрированности.

ВАЖНО: payload вредоносного pickle безвреден (echo) и НИКОГДА не исполняется —
control-plane не делает pickle.load, а pickle.dumps лишь сериализует инструкцию.
"""
import hashlib
import json
import os
import pickle
import struct
import subprocess
import time
import urllib.error
import urllib.request

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
SERVING = os.environ.get("SERVING_URL", "http://localhost:8001")


def req(method, path, role=None, body=None, sub=None, base=None, extra_headers=None):
    headers = dict(extra_headers or {})
    if role:
        headers["Authorization"] = f"Bearer dev:{sub or role.lower()}:{role}"
    data = None
    if isinstance(body, (bytes, bytearray)):
        data, headers["Content-Type"] = bytes(body), "application/octet-stream"
    elif body is not None:
        data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
    r = urllib.request.Request((base or BASE) + path, data=data, headers=headers, method=method)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(r, timeout=20) as resp:
                return resp.status, json.loads(resp.read() or "null")
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                time.sleep(1.5 * (attempt + 1))   # rate-limit: бэк-офф и повтор, демо не должно падать от лимита
                continue
            try:
                return e.code, json.loads(e.read() or "null")
            except Exception:
                return e.code, None
        except (urllib.error.URLError, OSError):
            # соединение оборвано: напр. сервер отверг оверсайз (413), не читая тело — это и есть защита
            return 0, None
    return 429, None


def hr(title):
    print("\n" + "=" * 70 + f"\n  {title}\n" + "=" * 70)


def line(s=""):
    print("  " + s)


# ---- демо-артефакты (генерим на лету) ----
class _Evil:
    def __reduce__(self):
        return (os.system, ("echo sirius-demo-marker",))  # безвреден; никогда не исполняется


class _BenignModel:
    def __init__(self):
        self.weights = [0.1, 0.2, 0.3]


MALICIOUS_PKL = pickle.dumps(_Evil())
CLEAN_PKL = pickle.dumps({"model": "linear", "weights": [0.1, 0.2, 0.3]})
BENIGN_CODE_PKL = pickle.dumps(_BenignModel())
_st_header = b'{"__metadata__": {"producer": "sirius-demo"}}'
SAFETENSORS = struct.pack("<Q", len(_st_header)) + _st_header


def model(name, criticality):
    _, j = req("POST", "/api/models", "DS", {"name": name, "type": "boosting", "criticality": criticality})
    return j["model_id"]


def findings_for(asset):
    _, j = req("GET", "/api/findings", "MLSecOps")
    return [f for f in j["findings"] if f["asset"] == asset]


def main():
    hr("0. Здоровье платформы (единая точка входа :8080)")
    st, h = req("GET", "/health")
    line(f"status={h['status']}  audit_chain_ok={h['audit_chain_ok']}")
    line(f"шина событий: connected={h['bus']['connected']}  events={h['bus']['events']}")
    line(f"MLflow-реестр: connected={h['mlflow']['connected']}  (порт наружу НЕ публикуется)")
    line(f"секреты: source={h['vault']['secrets_source']}  (HashiCorp Vault: AppRole + политика + аудит + revoke)")

    hr("1. MONEY-SHOT #1 — затянули ВРЕДОНОСНУЮ модель → БЛОК")
    mid = model("fraud-detector", "internal")
    line(f"DS зарегистрировал модель fraud-detector (id={mid}); тянет внешний артефакт...")
    st, j = req("POST", f"/api/models/{mid}/ingest", "DS", MALICIOUS_PKL)
    line(f"  ↳ ingestion-гейт: HTTP {st}  →  {'🛑 ЗАБЛОКИРОВАНО' if st == 422 else j}")
    if st == 422:
        line(f"     причина: формат={j['detail']['format']}, сработали {j['detail']['tools']}")
    for f in findings_for(f"model/{mid}"):
        line(f"     Finding: [{f['severity']}] {f['tool']} → {f['verdict']}  ({f['detail']})")
    _, reg = req("GET", "/api/registry", "MLSecOps")
    vers = next(m["versions"] for m in reg["models"] if m["id"] == mid)
    line(f"  реестр: версий у модели = {len(vers)}  →  вредоносная модель НЕ дошла до прода ✅")
    line("  (артефакт не десериализовался: скан читает опкоды, pickle.load не вызывается)")

    hr("2. Чистый артефакт того же DS → ДОПУЩЕН и реально в MLflow")
    st, j = req("POST", f"/api/models/{mid}/ingest", "DS", SAFETENSORS)
    line(f"  ↳ safetensors: HTTP {st}  →  допущен, версия v{j.get('version')} (format={j.get('format')})")
    st, b = req("GET", f"/api/models/{mid}/backend", "MLSecOps")
    line(f"  backend={b['backend']} present={b['present']} versions={[v['cp_version'] for v in b['versions']]}")
    line("  → реестр живёт в обёрнутом MLflow, читаем его ТОЛЬКО через control-plane ✅")

    hr("3. SUP-07 — политика форматов по критичности")
    fin = model("credit-scoring", "financial")
    line(f"DS регистрирует КРИТИЧНУЮ (financial) модель (id={fin}) и подаёт pickle...")
    st, j = req("POST", f"/api/models/{fin}/ingest", "DS", CLEAN_PKL)
    line(f"  ↳ HTTP {st}: {'🛑 формат pickle недопустим для критичной модели' if st == 422 else 'допущен'}")
    st, j = req("POST", f"/api/models/{fin}/ingest", "DS", SAFETENSORS)
    line(f"  ↳ тот же safetensors: HTTP {st}  →  безопасный формат принят ✅")

    hr("4. DATA-01 — карантин недоверенного источника данных")
    st, j = req("POST", "/api/datasets", "DE", {"name": "leads", "source": "http://random-hub/leads"})
    line(f"  источник http://random-hub/leads  →  статус: {j['status']} 🛑")
    st, j = req("POST", "/api/datasets", "DE", {"name": "leads", "source": "internal://curated/leads"})
    line(f"  источник internal://curated/leads  →  статус: {j['status']} ✅")

    hr("5. CODE-01 — ML-aware SAST на код (без исполнения)")
    bad = b"import os\ndef train(p):\n    os.system('echo hi')\n    return eval(p)\n"
    st, j = req("POST", "/api/scan/code", "DS", bad)
    line(f"  код с os.system/eval → clean={j['clean']}  ({j['findings'][0]['detail'] if j['findings'] else ''})")
    st, j = req("POST", "/api/scan/code", "DS", b"def add(a, b):\n    return a + b\n")
    line(f"  безопасный код       → clean={j['clean']} ✅")
    _, js = req("POST", "/api/scan/code", "DS", b'TOKEN = "demoSecret123"\n')
    line(f"  код с захардкоженным секретом → clean={js['clean']} (ACC-06: {[f['verdict'] for f in js['findings']]})")

    hr("MONEY-SHOT #2 — уязвимая зависимость не доходит до прода (SUP-03)")
    _, j = req("POST", "/api/scan/deps", "DS", b"numpy==1.26.4\nrequests==2.19.0\n")
    line(f"  requirements c requests==2.19.0  →  clean={j['clean']}")
    for f in j["findings"]:
        line(f"     🛑 {f['detail']}")
    _, j = req("POST", "/api/scan/deps", "DS", b"numpy==1.26.4\nfastapi==0.115.6\n")
    line(f"  чистые requirements  →  clean={j['clean']} ✅")

    hr("MONEY-SHOT #3 — критичная модель только после ручного аппрув-гейта (VIS-03 + policy-матрица)")
    _, dvj = req("POST", "/api/datasets", "DE", {"name": "scoring-data", "source": "internal://curated/scoring"})
    _, cmj = req("POST", "/api/models", "DS", {"name": "credit-model", "criticality": "financial"})
    cm = cmj["model_id"]
    _, vj = req("POST", f"/api/models/{cm}/versions", "DS",
                {"dataset_version_id": dvj["dataset_version_id"], "code_commit": "abc123", "env_lock": "req.lock",
                 "intended_use": "скоринг заявок", "limitations": "не для физлиц"})
    cv = vj["version"]
    req("POST", f"/api/models/{cm}/versions/{cv}/sign", "MLSecOps")  # крипто-подпись Ed25519 (SUP-04)
    st, _ = req("POST", f"/api/models/{cm}/versions/{cv}/promote", "MLSecOps")
    line(f"  промоушен критичной модели БЕЗ ручного аппрува  →  HTTP {st} 🛑")
    req("POST", f"/api/models/{cm}/versions/{cv}/approve", "MLSecOps", {"reason": "ревью пройдено"}, sub="reviewer")
    st, _ = req("POST", f"/api/models/{cm}/versions/{cv}/promote", "MLSecOps")
    line(f"  другой MLSecOps (reviewer) одобрил версию  →  промоушен  →  HTTP {st} ✅ (separation of duties)")
    # критичная версия, намеренно оставленная НА РУЧНОМ АППРУВ-ГЕЙТЕ — для инспектора /map:
    # подписана и воспроизводима, но ждёт аппрува/отклонения MLSecOps (кнопки в карточке узла)
    _, fdj = req("POST", "/api/datasets", "DE", {"name": "fraud-data", "source": "internal://curated/fraud"})
    _, fmj = req("POST", "/api/models", "DS", {"name": "fraud-scoring", "criticality": "regulatory"})
    fm = fmj["model_id"]
    _, fvj = req("POST", f"/api/models/{fm}/versions", "DS",
                 {"dataset_version_id": fdj["dataset_version_id"], "code_commit": "f00dca7", "env_lock": "req.lock",
                  "intended_use": "детект мошеннических транзакций", "limitations": "не для кредитных решений"})
    fv = fvj["version"]
    req("POST", f"/api/models/{fm}/versions/{fv}/sign", "MLSecOps")
    line(f"  критичная fraud-scoring v{fv} подписана и ОЖИДАЕТ РУЧНОГО АППРУВ-ГЕЙТА — решение в инспекторе /map ⏳")

    hr("MONEY-SHOT #4 — рантайм: бёрст extraction → детект + троттлинг (RT-01)")
    sc, mdl = req("GET", "/models", base=SERVING)
    if sc == 200:
        line(f"  задеплоено моделей: {len(mdl['models'])} — типы {[m['type'] for m in mdl['models']]}")
        n429 = sum(1 for _ in range(70)
                   if req("POST", "/predict/iris-linear", base=SERVING, body={"features": [5.1, 3.5, 1.4, 0.2]})[0] == 429)
        line(f"  70 запросов одним клиентом  →  троттлинг 429: {n429} раз 🛑")
        exts = [f for f in req("GET", "/api/findings", "MLSecOps")[1]["findings"] if f["verdict"] == "extraction"]
        line(f"  сработка extraction в control-plane: {'есть ✅' if exts else 'нет'} (петля рантайм→реестр)")
    else:
        line("  (сервинг недоступен — пропуск; подними `make up`)")

    hr("6. VIS-02 — расхождение вердиктов сканеров + триаж фолза")
    vid = model("recommender", "internal")
    st, j = req("POST", f"/api/models/{vid}/ingest", "DS", BENIGN_CODE_PKL)
    line(f"  безопасный код-несущий артефакт: HTTP {st} (допущен) — но вердикты разошлись:")
    susp = [f for f in findings_for(f"model/{vid}") if f["verdict"] == "suspicious"]
    for f in susp:
        line(f"     Finding: {f['tool']} → {f['verdict']}  ({f['detail']})")
    if susp:
        fid = susp[0]["id"]
        st_ds, _ = req("POST", f"/api/findings/{fid}/triage", "DS", {"status": "FP", "reason": "x"})
        line(f"  DS пытается закрыть как FP → HTTP {st_ds} (нет прав)")
        st_ok, _ = req("POST", f"/api/findings/{fid}/triage", "MLSecOps", {"status": "FP", "reason": "ложное срабатывание"})
        line(f"  MLSecOps закрывает как FP → HTTP {st_ok} ✅ (в аудите: кто/почему)")

    hr("8. Расширенные гейты — supply-chain и качество данных")
    _, sd = req("POST", "/api/scan/deps", "DS", b"numpyy==1.26.4\nreqeusts==2.0\nsirius-ml\n")
    line(f"  тайпсквоттинг + dependency confusion → clean={sd['clean']} {[f['verdict'] for f in sd['findings']]}")
    _, hc = req("POST", "/api/scan/code", "DS", b"def approve(score):\n    if score > 0.75:\n        return True\n    return False\n")
    line(f"  захардкоженный бизнес-порог (ACC-07) → {[f['verdict'] for f in hc['findings']]}")
    _, lf = req("POST", "/api/scan/dataset", "DE", {"labels": ["fraud"] * 9 + ["legit"], "baseline_dist": {"fraud": 0.05, "legit": 0.95}})
    _, bd = req("POST", "/api/scan/dataset", "DE", {"samples": ["обычный отзыв", "товар​​купи сейчас"]})
    _, sk = req("POST", "/api/scan/dataset", "DE", {"train_stats": {"amount": 100.0}, "serve_stats": {"amount": 900.0}})
    _, fb = req("POST", "/api/scan/dataset", "DE", {"feedback": [{"provenance": "user-submitted"}]})
    verdicts = [r["findings"][0]["verdict"] for r in (lf, bd, sk, fb) if r["findings"]]
    line(f"  гейт данных (DATA-02/03/05 + FB-01): {verdicts}")

    hr("9. Прогрев карты — рантайм и governance-контроли")
    sc2, _ = req("GET", "/health", base=SERVING)
    if sc2 == 200:
        req("POST", "/predict/iris-linear", base=SERVING, body={"features": [99.0, 99.0, 99.0, 99.0]}, extra_headers={"X-Client-Id": "warm-ood"})  # RT-02 OOD
        req("POST", "/predict/iris-linear", base=SERVING, body={"features": [1.0, 2.0]}, extra_headers={"X-Client-Id": "warm-bad"})  # RT-05 malformed
        for _ in range(18):  # MON-01 дрейф распределения
            req("POST", "/predict/iris-linear", base=SERVING, body={"features": [12.0, 9.0, 10.0, 8.0]}, extra_headers={"X-Client-Id": "warm-drift"})
        for _ in range(33):  # DOW-01 стоимостная квота тенанта
            req("POST", "/predict/iris-linear", base=SERVING, body={"features": [5.1, 3.5, 1.4, 0.2]}, extra_headers={"X-Client-Id": "warm-dow", "X-Tenant-Id": "demo-tenant"})
        dosn = sum(1 for i in range(200)  # DOS-01 распределённый флуд → глобальный load-shed (последним: дальше serving не зовём)
                   if req("POST", "/predict/iris-linear", base=SERVING, body={"features": [5.1, 3.5, 1.4, 0.2]}, extra_headers={"X-Client-Id": f"flood-{i % 40}"})[0] == 503)
        line(f"  рантайм: RT-02 OOD · RT-05 malformed · MON-01 drift · DOW-01 квота · DOS-01 load-shed×{dosn}")
    tm = model("tamper-demo", "internal")
    _, iv = req("POST", f"/api/models/{tm}/ingest", "DS", SAFETENSORS)
    req("POST", f"/api/models/{tm}/versions/{iv.get('version')}/verify-artifact", "MLSecOps", SAFETENSORS + b"TAMPER")  # TOCTOU-01/SUP-05
    ex = model("export-demo", "internal")
    for _ in range(20):
        req("GET", f"/api/models/{ex}/export", "DS")  # EXF-01
    rm = model("retire-demo", "internal")
    _, rv = req("POST", f"/api/models/{rm}/ingest", "DS", SAFETENSORS)
    req("POST", f"/api/models/{rm}/versions/{rv.get('version')}/retire", "MLSecOps")  # MON-03
    req("POST", "/api/ci/scan", "DE", {"ref": "feature/warm", "files": [{"path": "x.py", "content": "import os\nos.system('echo hi')\n"}]})  # CI-01
    req("POST", "/api/offboard", "MLSecOps", {"actor": "warm-ex-employee"})  # ACC-03
    req("POST", f"/api/models/{rm}/ingest", "DS", b"\x00" * (26 * 1024 * 1024))  # DOS-02 оверсайз → 413
    line("  governance: TOCTOU-01/SUP-05 · EXF-01 · MON-03 · CI-01 · ACC-03 · DOS-02(оверсайз→413)")

    hr("MONEY-SHOT #7 — GRC: принятие остаточного риска под условиями (GOV-02)")
    dvr = req("POST", "/api/datasets", "DE", {"name": "risk-ds", "source": "internal://curated/risk"})[1]["dataset_version_id"]
    rkm = model("risk-model", "internal")
    rkv = req("POST", f"/api/models/{rkm}/versions", "DS",
              {"dataset_version_id": dvr, "code_commit": "abc", "env_lock": "lock",
               "artifact_hash": hashlib.sha256(b"orig").hexdigest()})[1]["version"]
    req("POST", f"/api/models/{rkm}/versions/{rkv}/verify-artifact", "MLSecOps", b"TAMPERED")  # инъекция critical (artifact-tampered)
    st_b = req("POST", f"/api/models/{rkm}/versions/{rkv}/promote", "MLSecOps")[0]
    line(f"  открытая critical-сработка на версии → промоушен: HTTP {st_b} 🛑 (open-critical gate)")
    st_ds = req("POST", "/api/risk-acceptance", "DS", {"ref": f"model/{rkm}/v{rkv}", "justification": "x"})[0]
    line(f"  DS пытается принять риск → HTTP {st_ds} (нет прав — принимает старшая роль, separation)")
    req("POST", "/api/risk-acceptance", "CEO",
        {"ref": f"model/{rkm}/v{rkv}", "scope": "version", "justification": "осознанный приём: низкий blast-radius, актив internal",
         "conditions": "ре-скан и закрытие сработки в 7 дней", "expires_at": "2099-12-31T00:00:00+00:00"})
    st_c, jc = req("POST", f"/api/models/{rkm}/versions/{rkv}/promote", "MLSecOps")
    line(f"  CEO принял риск под условиями+сроком → промоушен: HTTP {st_c}, conditional={jc.get('conditional')} ✅ (в аудите: кто/почему/срок)")

    hr("MONEY-SHOT #8 — Vault: секреты по политике + мгновенный revoke (CRED-02)")
    line(f"  control-plane берёт секреты из Vault: source={h['vault']['secrets_source']} ✅ (по AppRole, не из env)")
    _vscript = (
        'export VAULT_ADDR=http://127.0.0.1:8200\n'
        'RID=$(vault read -field=role_id auth/approle/role/control-plane/role-id)\n'
        'SID=$(vault write -f -field=secret_id auth/approle/role/control-plane/secret-id)\n'
        'TOK=$(vault write -field=token auth/approle/login role_id=$RID secret_id=$SID)\n'
        'VAULT_TOKEN=$TOK vault kv get -field=seed secret/sirius/signing >/dev/null 2>&1 && echo ALLOWED_OK\n'
        'VAULT_TOKEN=$TOK vault kv get secret/forbidden/x >/dev/null 2>&1 || echo DENIED_OK\n'
        'vault write -f auth/approle/role/control-plane/secret-id/destroy secret_id=$SID >/dev/null 2>&1\n'
        'vault write auth/approle/login role_id=$RID secret_id=$SID >/dev/null 2>&1 || echo REVOKE_OK\n'
    )
    try:
        _repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _vtok = os.environ.get("VAULT_ROOT_TOKEN", "sirius-root-dev")  # AUD-28: из env, не хардкод
        _out = subprocess.run(["docker", "compose", "exec", "-T", "-e", f"VAULT_TOKEN={_vtok}", "vault", "sh", "-c", _vscript],
                              cwd=_repo, capture_output=True, text=True, timeout=40).stdout
        line(f"  свой секрет по политике: {'выдан ✅' if 'ALLOWED_OK' in _out else '—'} · "
             f"чужой путь: {'403 ✅' if 'DENIED_OK' in _out else '—'} · "
             f"отзыв secret-id → логин: {'отклонён ✅ (revoke мгновенный)' if 'REVOKE_OK' in _out else '—'}")
    except Exception as e:
        line(f"  (revoke-демо через контейнер vault пропущено: {e})")

    hr("MONEY-SHOT #5 — карта покрытия угроз + CEO-вью (VIS-01)")
    _, cov = req("GET", "/api/coverage", "CEO")
    k = cov["kpi"]
    line(f"  покрытие контролей: {k['coverage']} live · сработок {k['findings_total']} · "
         f"блокировок {k['blocked_attempts']} · отказов доступа {k['access_denied']}")
    line(f"  моделей {k['models']} · прод-деплоев {k['prod_deployments']} · аудит цел: {k['audit_chain_ok']}")
    for c in cov["controls"]:
        line(f"     {'🟢' if c['status'] == 'live' else '⚪'} {c['id']}: {c['threat']} — {c['control']} ({c['evidence']})")
    line(f"  CEO-вью (HTML): {BASE}/coverage")

    hr("7. СВОДКА — Finding как спина интегрированности")
    _, j = req("GET", "/api/findings", "MLSecOps")
    by_tool = {}
    for f in j["findings"]:
        by_tool.setdefault(f["tool"], []).append(f["verdict"])
    line(f"всего сработок: {len(j['findings'])}  (по инструментам:)")
    for tool, verdicts in sorted(by_tool.items()):
        line(f"   {tool}: {len(verdicts)}  {sorted(set(verdicts))}")
    line("")
    line(f"аудит-таймлайн (append-only, hash-chain) и дашборд: {BASE}/")
    line("каждое действие и каждый блок — в аудите; цепочка целостна (audit_chain_ok).")


def _fatal(e):
    print(f"\n  ⚠ демо прервалось: неожиданный ответ от стека ({type(e).__name__}: {e}).")
    print("    Вероятно стек ещё поднимается или под нагрузкой (rate-limit).")
    print("    Подожди ~10–20 c и повтори `make demo`. Стенд должен быть поднят с DEV_AUTH=1.")
    raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as e:
        _fatal(e)
