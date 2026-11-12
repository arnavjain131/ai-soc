from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = 'soc_workspaces'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(100))


class Membership(Base):
    __tablename__ = 'soc_memberships'
    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey('soc_workspaces.id'), index=True)
    role: Mapped[str] = mapped_column(String(10))


class Source(Base):
    __tablename__ = 'soc_sources'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey('soc_workspaces.id'), index=True)
    name: Mapped[str] = mapped_column(String(100))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Event(Base):
    __tablename__ = 'soc_events'
    __table_args__ = (
        UniqueConstraint('source_id', 'external_event_id'),
        Index('soc_event_detection', 'workspace_id', 'source_id', 'event_type', 'event_time'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey('soc_workspaces.id'), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey('soc_sources.id'))
    external_event_id: Mapped[str] = mapped_column(String(128))
    event_time: Mapped[datetime] = mapped_column(DateTime)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    event_type: Mapped[str] = mapped_column(String(32))
    source_ip: Mapped[str] = mapped_column(String(45))
    destination_ip: Mapped[str] = mapped_column(String(45))
    destination_port: Mapped[int] = mapped_column(Integer)
    username: Mapped[str] = mapped_column(String(128))
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)


class Incident(Base):
    __tablename__ = 'soc_incidents'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey('soc_workspaces.id'), index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(24), default='open')
    severity: Mapped[str] = mapped_column(String(10), default='high')
    risk_score: Mapped[int] = mapped_column(Integer, default=50)
    score_components: Mapped[dict] = mapped_column(JSON, default=lambda: {'rule_severity': 40, 'authentication_evidence': 10})
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Alert(Base):
    __tablename__ = 'soc_alerts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey('soc_workspaces.id'), index=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey('soc_incidents.id'), index=True)
    rule_key: Mapped[str] = mapped_column(String(40), default='brute_force_v1')
    dedup_key: Mapped[str] = mapped_column(String(64), unique=True)
    explanation: Mapped[str] = mapped_column(String(500))


class AlertEvent(Base):
    __tablename__ = 'soc_alert_events'
    alert_id: Mapped[str] = mapped_column(ForeignKey('soc_alerts.id'), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey('soc_events.id'), primary_key=True)


class Audit(Base):
    __tablename__ = 'soc_audit_logs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey('soc_workspaces.id'), index=True)
    actor: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[str] = mapped_column(String(36))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
