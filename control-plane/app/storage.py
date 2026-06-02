"""Карантин-стор артефактов в MinIO (S3).

Зачем: храним ПРОВЕРЕННЫЕ байты артефакта, чтобы подпись (model-signing) и
verify-on-consume шли по реальному артефакту, а не по одному только хэшу — это
закрывает провенанс-разрыв (что отсканировали и подписали = что уходит в прод).
MinIO во внутренней сети, наружу не публикуется. Fail-soft: если стор недоступен,
работаем по хэшу (как раньше), без падения.
"""
import logging
import os

logger = logging.getLogger("sirius")

_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "")          # http://minio:9000
_KEY = os.environ.get("AWS_ACCESS_KEY_ID", "")
_SECRET = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
_BUCKET = os.environ.get("ARTIFACT_BUCKET", "sirius-quarantine")
_client = None


def configured() -> bool:
    return bool(_ENDPOINT)


def _s3():
    global _client
    if _client is None and _ENDPOINT:
        import boto3
        from botocore.config import Config
        _client = boto3.client("s3", endpoint_url=_ENDPOINT, aws_access_key_id=_KEY,
                               aws_secret_access_key=_SECRET, region_name="us-east-1",
                               config=Config(retries={"max_attempts": 2}, connect_timeout=3, read_timeout=5))
        try:
            _client.head_bucket(Bucket=_BUCKET)
        except Exception:
            try:
                _client.create_bucket(Bucket=_BUCKET)
            except Exception as e:
                logger.warning("MinIO bucket %s недоступен: %s", _BUCKET, e)
    return _client


def put(key: str, data: bytes) -> str:
    """Сохранить байты по ключу. Возвращает ключ или '' (fail-soft)."""
    c = _s3()
    if c is None:
        return ""
    try:
        c.put_object(Bucket=_BUCKET, Key=key, Body=data)
        return key
    except Exception as e:
        logger.warning("MinIO put %s: %s", key, e)
        return ""


def get(key: str):
    """Прочитать байты по ключу или None."""
    c = _s3()
    if c is None or not key:
        return None
    try:
        return c.get_object(Bucket=_BUCKET, Key=key)["Body"].read()
    except Exception as e:
        logger.warning("MinIO get %s: %s", key, e)
        return None
