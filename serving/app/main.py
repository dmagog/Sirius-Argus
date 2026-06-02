"""Sirius Argus — Serving.

Три НЕ-генеративные модели разных типов (бустинг-классификатор, линейный
классификатор, anomaly-detection), обученные на синтетике на старте (CPU, быстро).
Рантайм-защиты: rate-limit + детект экстракции (бёрст одного клиента → 429, RT-01).
При детекте — обратная связь в control-plane: Finding(extraction) + аудит
(петля рантайм→реестр). Сервинг наружу публикуется (второй контур кроме proxy).
"""
import logging
import os
import time
from collections import defaultdict, deque

import numpy as np
import requests
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from sklearn.datasets import load_iris
from sklearn.ensemble import GradientBoostingClassifier, IsolationForest
from sklearn.linear_model import LogisticRegression

logger = logging.getLogger("serving")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s serving %(message)s")

app = FastAPI(title="Sirius Argus — Serving")
CONTROL_PLANE = os.environ.get("CONTROL_PLANE_URL", "http://control-plane:8000")
SERVICE_TOKEN = os.environ.get("SERVICE_TOKEN", "dev:serving:MLSecOps")
FEATURES = 4

# extraction-detect: скользящее окно запросов по клиенту
_WINDOW_S = 10.0
_THRESHOLD = 50
_hits = defaultdict(deque)
_reported = set()

# DOS-01: глобальный load-shedding (распределённый флуд по многим клиентам)
_GLOBAL_WINDOW_S = 10.0
_GLOBAL_THRESHOLD = 150
_global = deque()
_ANOMALY = None  # RT-02: модель аномалий как OOD/adversarial-детектор

MODELS = {}


@app.on_event("startup")
def _startup():
    data = load_iris()  # реальные данные (bundled в sklearn, без egress): 150×4, 3 класса
    X, y = data.data, data.target
    names = list(data.target_names)
    MODELS["iris-boosting"] = {"type": "boosting", "task": "classification", "dataset": "iris", "labels": names,
                               "est": GradientBoostingClassifier(n_estimators=40, max_depth=2, random_state=42).fit(X, y)}
    MODELS["iris-linear"] = {"type": "linear", "task": "classification", "dataset": "iris", "labels": names,
                             "est": LogisticRegression(max_iter=500).fit(X, y)}
    MODELS["iris-anomaly"] = {"type": "anomaly", "task": "anomaly-detection", "dataset": "iris", "labels": ["inlier", "outlier"],
                              "est": IsolationForest(n_estimators=80, random_state=42).fit(X)}
    global _ANOMALY
    _ANOMALY = MODELS["iris-anomaly"]["est"]
    logger.info("обучены модели на iris: %s", sorted(MODELS))


class PredictIn(BaseModel):
    features: list[float]


def _client(req: Request) -> str:
    return req.headers.get("x-client-id") or (req.client.host if req.client else "anon")


def _rate(client: str) -> int:
    now = time.monotonic()
    dq = _hits[client]
    dq.append(now)
    while dq and now - dq[0] > _WINDOW_S:
        dq.popleft()
    return len(dq)


def _global_rate() -> int:
    now = time.monotonic()
    _global.append(now)
    while _global and now - _global[0] > _GLOBAL_WINDOW_S:
        _global.popleft()
    return len(_global)


def _report(client: str, model: str, etype: str, count: int = 0):
    """Унифицированный отчёт о рантайм-детекте в control-plane (→ Finding + audit).
    Дедуп по (client, model, type), чтобы не флудить."""
    key = (model, etype) if etype == "ddos" else (client, model, etype)  # ddos — глобальное событие, не на клиента
    if key in _reported:
        return
    _reported.add(key)
    try:
        requests.post(f"{CONTROL_PLANE}/api/runtime/event",
                      headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
                      json={"type": etype, "endpoint": model, "client": client, "count": count}, timeout=3)
    except requests.RequestException as e:
        logger.warning("рантайм-событие %s не доставлено в control-plane: %s", etype, e)


@app.get("/health")
def health():
    return {"status": "ok", "service": "serving", "models": sorted(MODELS)}


@app.get("/models")
def models():
    return {"models": [{"name": n, "type": m["type"], "task": m["task"], "dataset": m.get("dataset"), "features": FEATURES}
                       for n, m in sorted(MODELS.items())]}


@app.post("/predict/{name}")
def predict(name: str, body: PredictIn, request: Request):
    if name not in MODELS:
        raise HTTPException(status_code=404, detail="model not found")
    client = _client(request)
    if _global_rate() > _GLOBAL_THRESHOLD:  # DOS-01: распределённый флуд → load-shedding
        _report(client, name, "ddos")
        raise HTTPException(status_code=503, detail=f"load-shedding: глобальный лимит {_GLOBAL_THRESHOLD}/{int(_GLOBAL_WINDOW_S)}s (DOS-01)")
    count = _rate(client)
    if count > _THRESHOLD:  # RT-01: бёрст одного клиента → экстракция
        _report(client, name, "extraction", count)
        raise HTTPException(status_code=429, detail=f"extraction/rate limit: {count} за {int(_WINDOW_S)}s — троттлинг (RT-01)")
    try:  # RT-05: malformed-вход смягчён (422), сервис не падает
        x = np.array(body.features, dtype=float).reshape(1, -1)
        if x.shape[1] != FEATURES:
            raise ValueError(f"нужно {FEATURES} признака(ов), пришло {x.shape[1]}")
    except (ValueError, TypeError) as e:
        _report(client, name, "malformed-input")
        raise HTTPException(status_code=422, detail=f"malformed input (RT-05): {e}")
    raw = int(MODELS[name]["est"].predict(x)[0])
    if MODELS[name]["type"] == "anomaly":
        label = "outlier" if raw == -1 else "inlier"
    else:
        lbls = MODELS[name].get("labels") or []
        label = lbls[raw] if 0 <= raw < len(lbls) else str(raw)
    suspect = False  # RT-02: OOD/adversarial — модель аномалий помечает вход выбросом
    try:
        if _ANOMALY is not None and int(_ANOMALY.predict(x)[0]) == -1:
            suspect = True
            _report(client, name, "adversarial-suspect")
    except Exception:
        pass
    return {"model": name, "type": MODELS[name]["type"], "prediction": raw, "label": label, "adversarial_suspect": suspect}
