from sqlalchemy import JSON, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import SessionType


class PointsLog(Base):
    __tablename__ = "points_log"
    __table_args__ = (
        UniqueConstraint("user_id", "event_id", "session_type", name="uq_points_log_user_event_session"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    session_type: Mapped[SessionType] = mapped_column(Enum(SessionType), nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, nullable=True)

    user: Mapped["User"] = relationship()
    event: Mapped["Event"] = relationship()
