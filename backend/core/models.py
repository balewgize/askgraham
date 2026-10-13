"""SQLAlchemy declarative base.

Kept in its own module so `alembic/env.py` and the application agree on a single
metadata object. Table definitions land in `models.py` (Phase 3).
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models."""
