from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.tables import utcnow


class QualityGrant(Base):
    __tablename__ = "qa_grants"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    capabilities: Mapped[list] = mapped_column(JSON, default=list)


class QualityCaseVersion(Base):
    __tablename__ = "qa_case_versions"
    __table_args__ = (UniqueConstraint("family_id", "version", name="uq_qa_case_version"),)
    id: Mapped[str] = mapped_column(String(12), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(12), index=True)
    version: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    state: Mapped[str] = mapped_column(String(16), default="candidate")
    specification: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class QualityPlan(Base):
    __tablename__ = "qa_plans"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    digest: Mapped[str] = mapped_column(String(64), default="")
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)


class QualityRun(Base):
    __tablename__ = "qa_runs"
    __table_args__ = (UniqueConstraint("user_id", "request_key", name="uq_qa_run_request"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("qa_plans.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    request_key: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(20))
    mode: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)


class QualityResult(Base):
    __tablename__ = "qa_results"
    __table_args__ = (UniqueConstraint("run_id", "case_id", name="uq_qa_result_case"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("qa_runs.id"), index=True)
    case_id: Mapped[str] = mapped_column(String(12))
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(24), default="queued")
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)


class QualityReportBatch(Base):
    __tablename__ = 'qa_report_batches'
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    request_key: Mapped[str] = mapped_column(String(80), unique=True)
    requested_cases: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class QualityReportMember(Base):
    __tablename__ = 'qa_report_members'
    # 不外键绑定run：原始执行仍按已有保留策略清理，汇总明确显示缺失证据。
    run_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey('qa_report_batches.id'), index=True)
    position: Mapped[int] = mapped_column(default=0)
