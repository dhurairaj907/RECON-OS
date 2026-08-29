"""
RECON OS — Application Configuration

Loads settings from environment variables / .env file.
All secrets are accessed ONLY through this module.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """Central configuration for the RECON OS backend."""

    model_config = SettingsConfigDict(
        env_file="../../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database ---
    DATABASE_URL: str = "postgresql://recon:recon_secret@localhost:5432/reconos"

    # --- Razorpay ---
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    # --- Application ---
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]
    DEFAULT_MERCHANT_NAME: str = "RECON Demo Merchant"

    # --- Phase 2 (THINK): Intelligence pipeline ---
    # When True, a new recovery case is analysed automatically after the Phase 1
    # transaction commits (in a separate, isolated transaction). The manual
    # analyze endpoint works regardless of this flag.
    INTELLIGENCE_ENABLED: bool = False
    INTELLIGENCE_VERSION: str = "1.0"

    # --- Policy Engine constants (deterministic, authoritative, operator-tunable) ---
    POLICY_MAX_RECOVERY_ATTEMPTS: int = 3
    POLICY_CONTACT_WINDOW_HOURS: int = 24
    POLICY_MAX_CONTACTS_PER_WINDOW: int = 1
    POLICY_AUTO_APPROVAL_AMOUNT_LIMIT: float = 5000.0

    # --- Phase 2 (optional, later): LLM provider abstraction ---
    # The system is fully functional with LLM_ENABLED=false using the
    # deterministic intelligence core. Keys are server-side only and must never
    # be exposed to the frontend.
    LLM_ENABLED: bool = False
    LLM_PROVIDER: str = ""
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""


settings = Settings()
