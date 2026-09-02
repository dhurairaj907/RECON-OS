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
    _run_lightweight_migrations()
    logger.info("Database tables created / verified")


def _run_lightweight_migrations():
    """
    Additive, idempotent column top-ups for tables that already exist in an older
    dev database (there is no Alembic in this project). SQLite and PostgreSQL
    both support `ALTER TABLE ... ADD COLUMN`. Never drops or rewrites data.
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    tables = set(insp.get_table_names())

    wanted = {
        "case_intelligence": {
            "provider_version": "VARCHAR(60)",
            "intelligence_version": "VARCHAR(20)",
            "ml_predictions_json": "TEXT",
            # Phase 10 — see models/case_intelligence.py::intent_json/intent_classification
            "intent_json": "TEXT",
            "intent_classification": "VARCHAR(30)",
            "intent_confidence": "NUMERIC(5,4)",
        },
        "recovery_actions": {
            "simulated": "BOOLEAN NOT NULL DEFAULT 0",
            "human_decision": "VARCHAR(20)",
            "human_decided_at": "TIMESTAMP",
            "human_decided_by": "VARCHAR(60)",
            # Phase 9 — see models/recovery_action.py::fulfilling_payment_id
            "fulfilling_payment_id": "VARCHAR(36)",
        },
        "merchants": {
            "organization_id": "VARCHAR(36)",
        },
        "customers": {
            "opted_out_channels": "VARCHAR(120)",
        },
        "communications": {
            "idempotency_key": "VARCHAR(200)",
            "last_webhook_event_id": "VARCHAR(120)",
        },
        "recovery_cases": {
            "simulated": "BOOLEAN NOT NULL DEFAULT 0",
        },
        # Phase 9 — payment lifecycle / reconciliation (additive only; see
        # models/payment.py and services/reconciliation.py).
        "payments": {
            "lifecycle_status": "VARCHAR(20)",
            "reconciliation_status": "VARCHAR(20) DEFAULT 'UNVERIFIED'",
            "refunded_amount_paise": "BIGINT NOT NULL DEFAULT 0",
            "dispute_status": "VARCHAR(20)",
        },
        "revenue_events": {
            "correlation_id": "VARCHAR(255)",
            "signature_verified": "BOOLEAN",
        },
    }

    for table, columns in wanted.items():
        if table not in tables:
            continue
        existing = {c["name"] for c in insp.get_columns(table)}
        missing = {name: ddl for name, ddl in columns.items() if name not in existing}
        if not missing:
            continue
        with engine.begin() as conn:
            for name, ddl in missing.items():
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
        logger.info("Migrated %s: added columns %s", table, list(missing))


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


def ensure_default_organization(db: Session):
    """
    Phase 5 backfill: any Merchant created before Phase 5 (organization_id IS
    NULL — including the existing recon_dev.db data) is assigned to a single
    default Organization. Additive only — never destroys or resets data.
    """
    from models.merchant import Merchant
    from models.organization import Organization

    orphans = db.query(Merchant).filter(Merchant.organization_id.is_(None)).all()
    if not orphans:
        return None

    default_org = (
        db.query(Organization).filter(Organization.name == settings.DEFAULT_ORGANIZATION_NAME).first()
    )
    if default_org is None:
        default_org = Organization(name=settings.DEFAULT_ORGANIZATION_NAME)
        db.add(default_org)
        db.commit()
        db.refresh(default_org)
        logger.info(f"Created default organization: {default_org.name} ({default_org.id})")

    for m in orphans:
        m.organization_id = default_org.id
    db.commit()
    logger.info(f"Backfilled {len(orphans)} pre-Phase-5 merchant(s) onto {default_org.name}")
    return default_org


def get_org_merchant(db: Session, organization):
    """
    Phase 5 — the organization-scoped replacement for `seed_default_merchant`.
    Finds (or creates) the single Merchant row belonging to `organization`.
    Routers now resolve `organization` from the authenticated session (see
    auth.get_current_organization) instead of trusting any client-supplied id.
    """
    from models.merchant import Merchant

    existing = db.query(Merchant).filter(Merchant.organization_id == organization.id).first()
    if existing:
        return existing

    merchant = Merchant(name=f"{organization.name} Merchant", organization_id=organization.id)
    db.add(merchant)
    db.commit()
    db.refresh(merchant)
    logger.info(f"Created merchant for organization {organization.name}: {merchant.id}")
    return merchant


def resolve_connected_merchant(db: Session):
    """
    Phase 8 — the organization-scoped merchant resolver for INBOUND provider
    webhooks (replaces `seed_default_merchant`, which just returned
    `db.query(Merchant).first()` with no ordering — "whichever merchant the
    database happens to return first". That only looked safe because
    exactly one merchant existed; since `POST /auth/register` already lets
    anyone create a second organization, it was a latent, non-deterministic
    cross-tenant misattribution bug.

    RECON OS has a single, platform-wide Razorpay credential today (see
    config.py) — there is no per-organization credential store, so an
    inbound webhook cannot be routed to "the organization that actually
    owns this Razorpay account" the way a true multi-tenant platform would.
    What this function guarantees instead is *deterministic, org-model-
    consistent* routing:
      - exactly one Organization exists (the common case) -> its Merchant,
        via `get_org_merchant` — the same resolver every other org-scoped
        router already uses;
      - no Organization exists yet -> bootstrap the platform default one;
      - more than one Organization exists, and EXACTLY ONE has a real
        registered user -> that one, regardless of name (a production
        deployment's common real shape: the empty auto-seeded platform-
        default org from first boot, plus the operator's own registered
        org — see the inline comment below for the incident this fixes);
      - more than one Organization exists and that's still ambiguous ->
        prefer the platform's named default organization if present, else
        the oldest by creation time (deterministic, unlike the old
        unordered first-row lookup).
    True multi-tenant webhook routing needs per-organization credentials —
    out of scope until that exists; this is documented on the Connections
    page and in the phase report as a known limitation, not hidden.
    """
    from models.organization import Organization

    ensure_default_organization(db)  # backfills any pre-Phase-5 orphan merchants; harmless no-op otherwise

    organizations = db.query(Organization).order_by(Organization.created_at).all()

    if not organizations:
        default_org = Organization(name=settings.DEFAULT_ORGANIZATION_NAME)
        db.add(default_org)
        db.commit()
        db.refresh(default_org)
        logger.info(f"Created default organization: {default_org.name} ({default_org.id})")
        return get_org_merchant(db, default_org)

    if len(organizations) == 1:
        return get_org_merchant(db, organizations[0])

    # Production bug fix: `seed_default_merchant` + `ensure_default_organization`
    # unconditionally create an empty, user-less "platform default" Organization
    # on the very first backend boot — before anyone has ever registered. Once a
    # real operator registers (POST /auth/register always creates a NEW,
    # differently-named Organization — see routers/auth.py), the deployment
    # ends up with >1 Organization: the auto-seeded empty one, and the real
    # one with the operator's actual login. The name-match tie-break below
    # would then ALWAYS prefer the empty auto-seeded org (it matches
    # DEFAULT_ORGANIZATION_NAME) over the operator's real one — every
    # webhook gets silently attributed to an organization nobody can log
    # into, while the operator's own dashboard correctly (from an isolation
    # standpoint) shows nothing. An Organization with zero registered users
    # can never be the one actually operating this deployment, so when
    # exactly one Organization among the candidates has a real user, prefer
    # it — unambiguous, and strictly more informative than a name match.
    # Falls through to the original name/oldest tie-break, UNCHANGED,
    # whenever this doesn't resolve unambiguously (zero or multiple
    # Organizations have real users) — never a regression for the
    # genuinely-ambiguous multi-tenant case this function already documents
    # as unsupported.
    from models.user_organization import UserOrganization

    org_ids = [o.id for o in organizations]
    populated_org_ids = {
        row[0] for row in
        db.query(UserOrganization.organization_id)
        .filter(UserOrganization.organization_id.in_(org_ids))
        .distinct()
        .all()
    }
    if len(populated_org_ids) == 1:
        populated_org = next(o for o in organizations if o.id in populated_org_ids)
        return get_org_merchant(db, populated_org)

    default_org = next((o for o in organizations if o.name == settings.DEFAULT_ORGANIZATION_NAME), None)
    return get_org_merchant(db, default_org or organizations[0])
