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

MODELS = {}


@app.on_event("startup")
def _startup():
    rng = np.random.RandomState(42)
    X = rng.randn(300, FEATURES)
    y = (X[:, 0] + X[:, 1] > 0).astype(int)
    MODELS["fraud-boosting"] = {"type": "boosting", "task": "classification",
                                "est": GradientBoostingClassifier(n_estimators=30, max_depth=2, random_state=42).fit(X, y)}
    MODELS["credit-linear"] = {"type": "linear", "task": "classification",
                               "est": LogisticRegression(max_iter=200).fit(X, y)}
    MODELS["traffic-anomaly"] = {"type": "anomaly", "task": "anomaly-detection",
                                 "est": IsolationForest(n_estimators=60, random_state=42).fit(X)}
    logger.info("обучены модели: %s", sorted(MODELS))


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


def _report_extraction(client: str, model: str, count: int):
    key = (client, model)
    if key in _reported:
        return
    _reported.add(key)
    try:
        requests.post(f"{CONTROL_PLANE}/api/runtime/event",
                      headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
                      json={"type": "extraction", "endpoint": model, "client": client, "count": count}, timeout=3)
    except requests.RequestException as e:
        logger.warning("событие extraction не доставлено в control-plane: %s", e)


@app.get("/health")
def health():
    return {"status": "ok", "service": "serving", "models": sorted(MODELS)}


@app.get("/models")
def models():
    return {"models": [{"name": n, "type": m["type"], "task": m["task"], "features": FEATURES}
                       for n, m in sorted(MODELS.items())]}


@app.post("/predict/{name}")
def predict(name: str, body: PredictIn, request: Request):
    if name not in MODELS:
        raise HTTPException(status_code=404, detail="model not found")
    client = _client(request)
    count = _rate(client)
    if count > _THRESHOLD:  # RT-01: бёрст одного клиента → детект экстракции + троттлинг
        _report_extraction(client, name, count)
        raise HTTPException(status_code=429, detail=f"extraction/rate limit: {count} запросов за {int(_WINDOW_S)}s — троттлинг (RT-01)")
    if len(body.features) != FEATURES:
        raise HTTPException(status_code=422, detail=f"нужно {FEATURES} признака(ов)")
    est = MODELS[name]["est"]
    pred = est.predict(np.array(body.features, dtype=float).reshape(1, -1))[0]
    return {"model": name, "type": MODELS[name]["type"], "prediction": int(pred)}
