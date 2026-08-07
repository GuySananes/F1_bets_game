from sqlalchemy import Boolean, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import BonusType


class BonusResult(Base):
    __tablename__ = "bonus_results"
    __table_args__ = (
        UniqueConstraint("event_id", "bonus_type", name="uq_bonus_result_event_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    bonus_type: Mapped[BonusType] = mapped_column(Enum(BonusType), nullable=False)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), nullable=True)
    bool_value: Mapped[bool] = mapped_column(Boolean, nullable=True)
    int_value: Mapped[int] = mapped_column(Integer, nullable=True)

    event: Mapped["Event"] = relationship()
    driver: Mapped["Driver"] = relationship()
