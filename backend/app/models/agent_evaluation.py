from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.models.tables import utcnow


class AgentEvaluation(Base):
    __tablename__='qa_agent_evaluations'
    id: Mapped[str]=mapped_column(String(32),primary_key=True)
    created_by: Mapped[int]=mapped_column(ForeignKey('users.id'))
    target: Mapped[str]=mapped_column(String(20),index=True)
    source_run: Mapped[str]=mapped_column(String(32),index=True)
    status: Mapped[str]=mapped_column(String(20),default='completed')
    snapshot: Mapped[dict]=mapped_column(JSON)
    program: Mapped[dict]=mapped_column(JSON)
    model_score: Mapped[dict]=mapped_column(JSON,default=dict)
    reviews: Mapped[list]=mapped_column(JSON,default=list)
    version: Mapped[int]=mapped_column(default=1)
    created_at: Mapped[datetime]=mapped_column(DateTime,default=utcnow)
