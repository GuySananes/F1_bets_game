from sqlalchemy import Boolean, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class EventEntry(Base):
    __tablename__ = "event_entries"
    __table_args__ = (UniqueConstraint("event_id", "driver_id", name="uq_event_entry_event_driver"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), nullable=False)
    is_substitute: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    substituted_for_driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), nullable=True)

    event: Mapped["Event"] = relationship(back_populates="entries")
    driver: Mapped["Driver"] = relationship(foreign_keys=[driver_id])
    substituted_for: Mapped["Driver"] = relationship(foreign_keys=[substituted_for_driver_id])
