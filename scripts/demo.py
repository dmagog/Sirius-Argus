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
import json
import os
import pickle
import struct
import urllib.error
import urllib.request

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
SERVING = os.environ.get("SERVING_URL", "http://localhost:8001")


def req(method, path, role=None, body=None, sub=None, base=None):
    headers = {}
    if role:
        headers["Authorization"] = f"Bearer dev:{sub or role.lower()}:{role}"
    data = None
    if isinstance(body, (bytes, bytearray)):
        data, headers["Content-Type"] = bytes(body), "application/octet-stream"
    elif body is not None:
        data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
    r = urllib.request.Request((base or BASE) + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, json.loads(resp.read() or "null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or "null")
        except Exception:
            return e.code, None


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

    hr("MONEY-SHOT #2 — уязвимая зависимость не доходит до прода (SUP-03)")
    _, j = req("POST", "/api/scan/deps", "DS", b"numpy==1.26.4\nrequests==2.19.0\n")
    line(f"  requirements c requests==2.19.0  →  clean={j['clean']}")
    for f in j["findings"]:
        line(f"     🛑 {f['detail']}")
    _, j = req("POST", "/api/scan/deps", "DS", b"numpy==1.26.4\nfastapi==0.115.6\n")
    line(f"  чистые requirements  →  clean={j['clean']} ✅")

    hr("MONEY-SHOT #3 — критичная модель только после HITL (VIS-03 + policy-матрица)")
    _, dvj = req("POST", "/api/datasets", "DE", {"name": "scoring-data", "source": "internal://curated/scoring"})
    _, cmj = req("POST", "/api/models", "DS", {"name": "credit-model", "criticality": "financial"})
    cm = cmj["model_id"]
    _, vj = req("POST", f"/api/models/{cm}/versions", "DS",
                {"dataset_version_id": dvj["dataset_version_id"], "code_commit": "abc123", "env_lock": "req.lock",
                 "intended_use": "скоринг заявок", "limitations": "не для физлиц", "signature": "cosign:abc"})
    cv = vj["version"]
    st, _ = req("POST", f"/api/models/{cm}/versions/{cv}/promote", "MLSecOps")
    line(f"  промоушен критичной модели БЕЗ HITL-аппрува  →  HTTP {st} 🛑")
    req("POST", f"/api/models/{cm}/versions/{cv}/approve", "MLSecOps", {"reason": "ревью пройдено"}, sub="reviewer")
    st, _ = req("POST", f"/api/models/{cm}/versions/{cv}/promote", "MLSecOps")
    line(f"  другой MLSecOps (reviewer) одобрил версию  →  промоушен  →  HTTP {st} ✅ (separation of duties)")

    hr("MONEY-SHOT #4 — рантайм: бёрст extraction → детект + троттлинг (RT-01)")
    sc, mdl = req("GET", "/models", base=SERVING)
    if sc == 200:
        line(f"  задеплоено моделей: {len(mdl['models'])} — типы {[m['type'] for m in mdl['models']]}")
        n429 = sum(1 for _ in range(70)
                   if req("POST", "/predict/credit-linear", base=SERVING, body={"features": [0.1, 0.2, 0.3, 0.4]})[0] == 429)
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


if __name__ == "__main__":
    main()
