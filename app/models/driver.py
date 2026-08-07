from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Driver(Base):
    __tablename__ = "drivers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_reserve: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    car_number: Mapped[int] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    season: Mapped["Season"] = relationship(back_populates="drivers")
    team: Mapped["Team"] = relationship(back_populates="drivers")
