"""Подпись артефактов моделей через OpenSSF **model-signing** (офлайн EC-ключ).

Не своя крипто-схема: `model_signing` подписывает РЕАЛЬНЫЕ байты артефакта (когда он сохранён
в карантин-сторе) и даёт стандартный манифест/подпись; верификация пересчитывает хэш и
проверяет публичным ключом. Офлайн private-key режим — без keyless Sigstore (egress нет; ADR-0006).

Когда подписываем: после ingest-скана и регистрации версии (sign-after-scan).
Что защищаем: целостность + провенанс — что в прод уходят ИМЕННО проверенные байты,
подписанные авторизованным ключом. Подпись ≠ безопасность (зловред ловит скан; подпись —
против подмены/несанкц. замены). Если байты артефакта недоступны (версия без загруженного
артефакта), подписываем канонический манифест model:ver:artifact_hash — деградация, но та же тулза.
Ключ — из SIGNING_KEY_PEM или детерминированно из SIGNING_SEED (демо; в проде — KMS/HSM/cosign).
"""
import hashlib
import os
import tempfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
import model_signing.signing as _sign
import model_signing.verifying as _verify


def _load_key():
    pem = os.environ.get("SIGNING_KEY_PEM")
    if pem:
        return serialization.load_pem_private_key(pem.encode(), password=None)
    seed_env = os.environ.get("SIGNING_SEED")
    # AUD-10: в проде (DEV_AUTH!=1) ключ подписи нельзя выводить из публичного дефолтного seed —
    # это обнулило бы SUP-04 (любой воспроизводит ключ из репозитория). Без ключа/seed — fail-fast.
    # В dev/тестах (DEV_AUTH=1) сохраняем демо-фолбэк, иначе стек не поднимется (SIGNING_SEED пуст).
    if not seed_env and os.environ.get("DEV_AUTH", "0") != "1":
        raise RuntimeError("AUD-10: задайте SIGNING_SEED или SIGNING_KEY_PEM из секрет-стора/KMS "
                           "(в проде ключ подписи не выводится из публичного дефолта)")
    seed = (seed_env or "5e1f17a0").encode()
    secret = (int.from_bytes(hashlib.sha256(seed).digest(), "big") % (2 ** 256 - 2)) + 1
    return ec.derive_private_key(secret, ec.SECP256R1())


_KEY = _load_key()
_DIR = tempfile.mkdtemp(prefix="sirius-signing-")
_PRIV = os.path.join(_DIR, "priv.pem")
_PUB = os.path.join(_DIR, "pub.pem")
with open(_PRIV, "wb") as _f:
    _f.write(_KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()))
with open(_PUB, "wb") as _f:
    _f.write(_KEY.public_key().public_bytes(serialization.Encoding.PEM,
                                            serialization.PublicFormat.SubjectPublicKeyInfo))


def _signed_object(model_id, ver, artifact_hash, artifact_bytes) -> bytes:
    """Что именно подписываем: реальные байты артефакта, если есть; иначе канонический манифест."""
    return artifact_bytes if artifact_bytes else f"{model_id}:{ver}:{artifact_hash or ''}".encode()


def sign(model_id, ver, artifact_hash: str = "", artifact_bytes: bytes = None) -> str:
    obj = _signed_object(model_id, ver, artifact_hash, artifact_bytes)
    with tempfile.TemporaryDirectory() as t:
        art, sig = os.path.join(t, "artifact"), os.path.join(t, "artifact.sig")
        with open(art, "wb") as f:
            f.write(obj)
        _sign.Config().use_elliptic_key_signer(private_key=_PRIV).sign(art, sig)
        with open(sig) as f:
            return f.read()


def verify(model_id, ver, artifact_hash: str = "", signature_bundle: str = "", artifact_bytes: bytes = None) -> bool:
    if not signature_bundle:
        return False
    obj = _signed_object(model_id, ver, artifact_hash, artifact_bytes)
    with tempfile.TemporaryDirectory() as t:
        art, sig = os.path.join(t, "artifact"), os.path.join(t, "artifact.sig")
        with open(art, "wb") as f:
            f.write(obj)
        with open(sig, "w") as f:
            f.write(signature_bundle)
        try:
            _verify.Config().use_elliptic_key_verifier(public_key=_PUB).verify(art, sig)
            return True
        except Exception:
            return False
