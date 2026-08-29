"""
RECON OS — Database Connection and Session Management

Provides the SQLAlchemy engine, session factory, and Base class.
Uses synchronous psycopg2 driver for simplicity in Phase 1.
"""

import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from config import settings

logger = logging.getLogger("recon.database")

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


def get_db():
    """
    FastAPI dependency — yields a database session and ensures cleanup.

    Usage:
        @router.get("/items")
        def list_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Create all tables on startup.
    Importing models ensures they are registered with Base.metadata.
    """
    import models  # noqa: F401 — triggers model registration
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created / verified")


def seed_default_merchant(db: Session):
    """
    Ensure a default merchant exists for Phase 1.
    Phase 1 operates as a single-merchant system.
    """
    from models.merchant import Merchant

    existing = db.query(Merchant).first()
    if existing:
        logger.info(f"Default merchant already exists: {existing.name} ({existing.id})")
        return existing

    merchant = Merchant(name=settings.DEFAULT_MERCHANT_NAME)
    db.add(merchant)
    db.commit()
    db.refresh(merchant)
    logger.info(f"Created default merchant: {merchant.name} ({merchant.id})")
    return merchant
