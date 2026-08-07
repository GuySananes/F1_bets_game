from typing import List

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    season: Mapped["Season"] = relationship(back_populates="teams")
    drivers: Mapped[List["Driver"]] = relationship(back_populates="team")
