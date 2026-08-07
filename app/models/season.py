from typing import List

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Season(Base):
    __tablename__ = "seasons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    default_grid_size: Mapped[int] = mapped_column(Integer, nullable=False)

    teams: Mapped[List["Team"]] = relationship(back_populates="season", cascade="all, delete-orphan")
    drivers: Mapped[List["Driver"]] = relationship(back_populates="season", cascade="all, delete-orphan")
    events: Mapped[List["Event"]] = relationship(back_populates="season", cascade="all, delete-orphan")
