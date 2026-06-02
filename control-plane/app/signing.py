"""Крипто-подпись версий моделей (ADR-0006), офлайн, без внешних бинарей.

Реальная Ed25519-подпись через `cryptography` (тянется как зависимость pyjwt[crypto]).
Платформа подписывает канонический message(model,ver,artifact_hash); промоушен
верифицирует подпись публичным ключом (SUP-04). Ключ — из SIGNING_SEED (демо;
в проде — HSM/KMS или офлайн-cosign-ключ, см. ADR-0006). «Подпись ≠ безопасность» —
она про целостность/провенанс, а не про отсутствие зловреда (для зловреда — сканы).
"""
import base64
import os

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_SEED = bytes.fromhex((os.environ.get("SIGNING_SEED") or "5e1f17a0").ljust(64, "0")[:64])
_KEY = Ed25519PrivateKey.from_private_bytes(_SEED)
_PUB = _KEY.public_key()


def _message(model_id, ver, artifact_hash: str) -> bytes:
    return f"{model_id}:{ver}:{artifact_hash or ''}".encode()


def sign(model_id, ver, artifact_hash: str = "") -> str:
    return base64.b64encode(_KEY.sign(_message(model_id, ver, artifact_hash))).decode()


def verify(model_id, ver, artifact_hash: str, signature: str) -> bool:
    if not signature:
        return False
    try:
        _PUB.verify(base64.b64decode(signature), _message(model_id, ver, artifact_hash))
        return True
    except (InvalidSignature, ValueError, Exception):
        return False
