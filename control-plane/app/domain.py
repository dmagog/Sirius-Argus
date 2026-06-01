"""Доменная модель реестра: датасеты, модели, версии, деплои.

ModelVersion несёт lineage (dataset_version + code_commit + env_lock) — для
репродьюсибилити (MON-02) и blast-radius, и поля профиля безопасности / модель-карты.
"""
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text

from .db import Base


class Dataset(Base):
    __tablename__ = "datasets"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    sensitivity = Column(String(16), default="open")  # open | pii | secret
    source = Column(String(255), default="")
    owner = Column(String(255), default="")


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    hash = Column(String(64), default="")


class DatasetColumn(Base):
    """Колонка датасета с пометкой PII (DATA-04): значения PII маскируются для ролей
    без допуска к чувствительным данным."""
    __tablename__ = "dataset_columns"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    name = Column(String(128), default="")
    is_pii = Column(Boolean, default=False)
    sample = Column(String(255), default="")


class Model(Base):
    __tablename__ = "models"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    type = Column(String(64), default="")              # boosting | linear | anomaly | ...
    criticality = Column(String(16), default="internal")  # regulatory | financial | mass | internal
    owner = Column(String(255), default="")


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id = Column(Integer, primary_key=True)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=False)
    version = Column(Integer, default=1)
    stage = Column(String(16), default="dev")          # dev | staging | prod | retired
    # lineage / репродьюсибилити (MON-02)
    dataset_version_id = Column(Integer, ForeignKey("dataset_versions.id"), nullable=True)
    code_commit = Column(String(64), default="")
    env_lock = Column(String(255), default="")
    # профиль безопасности / модель-карта (GOV-01)
    artifact_hash = Column(String(64), default="")
    signature = Column(String(128), default="")
    intended_use = Column(Text, default="")
    limitations = Column(Text, default="")
    requires_validation = Column(Boolean, default=False)


class Deployment(Base):
    __tablename__ = "deployments"
    id = Column(Integer, primary_key=True)
    model_version_id = Column(Integer, ForeignKey("model_versions.id"), nullable=False)
    status = Column(String(16), default="active")      # active | retired


class Finding(Base):
    """Сквозная «сработка»: инструмент, вердикт, severity, статус триажа, привязка
    к активу. Источник — гейты (скан моделей/данных/кода) и рантайм. Принцип
    «одна тулза ок, другая плохо»: на один актив может быть несколько Finding."""
    __tablename__ = "findings"
    id = Column(Integer, primary_key=True)
    ts = Column(String(32), default="")
    tool = Column(String(64), default="")
    verdict = Column(String(32), default="")            # malicious | suspicious | clean
    severity = Column(String(16), default="info")        # critical | high | medium | low | info
    status = Column(String(16), default="open")          # open | triaged | TP | FP
    asset_type = Column(String(32), default="")          # model | dataset | pr | endpoint
    asset_ref = Column(String(128), default="")
    detail = Column(Text, default="")
    actor = Column(String(255), default="")


class Approval(Base):
    """HITL-аппрув критичной версии (VIS-03): ручное одобрение MLSecOps перед
    промоушеном в прод. Кто/когда/почему — фиксируется и идёт в аудит."""
    __tablename__ = "approvals"
    id = Column(Integer, primary_key=True)
    model_version_id = Column(Integer, ForeignKey("model_versions.id"), nullable=False)
    approver = Column(String(255), default="")
    ts = Column(String(32), default="")
    reason = Column(Text, default="")
