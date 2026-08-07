from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    has_sprint: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    grid_size: Mapped[int] = mapped_column(Integer, nullable=False)

    # Predictions for a session lock automatically once its start time passes.
    # sprint_start_time is only set when has_sprint is true.
    qualifying_start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    sprint_start_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    race_start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    season: Mapped["Season"] = relationship(back_populates="events")
    entries: Mapped[List["EventEntry"]] = relationship(back_populates="event", cascade="all, delete-orphan")

    def start_time_for(self, session_type: str) -> Optional[datetime]:
        return {
            "qualifying": self.qualifying_start_time,
            "sprint": self.sprint_start_time,
            "race": self.race_start_time,
        }[session_type]

    def is_locked(self, session_type: str, now: Optional[datetime] = None) -> bool:
        start_time = self.start_time_for(session_type)
        if start_time is None:
            return False
        return (now or datetime.utcnow()) >= start_time
