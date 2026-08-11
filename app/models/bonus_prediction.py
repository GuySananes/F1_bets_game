from sqlalchemy import Boolean, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import BonusType


class BonusPrediction(Base):
    __tablename__ = "bonus_predictions"
    __table_args__ = (
        UniqueConstraint("user_id", "event_id", "bonus_type", name="uq_bonus_prediction_user_event_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    bonus_type: Mapped[BonusType] = mapped_column(Enum(BonusType), nullable=False)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), nullable=True)
    bool_value: Mapped[bool] = mapped_column(Boolean, nullable=True)
    int_value: Mapped[int] = mapped_column(Integer, nullable=True)
    is_auto_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped["User"] = relationship()
    event: Mapped["Event"] = relationship()
    driver: Mapped["Driver"] = relationship()
