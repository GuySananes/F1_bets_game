from sqlalchemy import Boolean, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import SessionType


class Result(Base):
    __tablename__ = "results"
    __table_args__ = (
        UniqueConstraint(
            "event_id", "session_type", "actual_position",
            name="uq_result_event_session_position",
        ),
        UniqueConstraint(
            "event_id", "session_type", "driver_id",
            name="uq_result_event_session_driver",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    session_type: Mapped[SessionType] = mapped_column(Enum(SessionType), nullable=False)
    actual_position: Mapped[int] = mapped_column(Integer, nullable=False)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), nullable=False)
    dnf: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    event: Mapped["Event"] = relationship()
    driver: Mapped["Driver"] = relationship()
