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

    # --- Phase 3 (ACT): Razorpay outbound (Payment Links) ---
    # TEST MODE ONLY. When False, action execution is refused (no accidental
    # live financial transactions). Credentials, if present, must be rzp_test_*.
    RAZORPAY_TEST_MODE: bool = True
    RAZORPAY_API_BASE: str = "https://api.razorpay.com/v1"
    RAZORPAY_TIMEOUT_SECONDS: float = 10.0

    # --- Application ---
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]
    DEFAULT_MERCHANT_NAME: str = "RECON Demo Merchant"

    # --- Phase 2 (THINK): Intelligence pipeline ---
    # When True, a new recovery case is analysed automatically after the Phase 1
    # transaction commits (in a separate, isolated transaction). The manual
    # analyze endpoint works regardless of this flag.
    INTELLIGENCE_ENABLED: bool = False
    INTELLIGENCE_VERSION: str = "2.5"

    # --- Policy Engine constants (deterministic, authoritative, operator-tunable) ---
    POLICY_MAX_RECOVERY_ATTEMPTS: int = 3
    POLICY_CONTACT_WINDOW_HOURS: int = 24
    POLICY_MAX_CONTACTS_PER_WINDOW: int = 1
    POLICY_AUTO_APPROVAL_AMOUNT_LIMIT: float = 5000.0

    # --- Phase 2.5 (REAL AI): LLM provider abstraction ---
    # The system is fully functional with LLM_ENABLED=false using the
    # deterministic intelligence core. Keys are server-side ONLY and must never
    # be exposed to the frontend, an API response, a log line, or a DB row.
    #
    # An LLM (Gemini) may ONLY assist diagnosis / explanation. It never touches
    # prediction, policy, financial authorisation, or Razorpay.
    LLM_ENABLED: bool = False
    LLM_PROVIDER: str = ""            # e.g. "gemini"
    LLM_API_KEY: str = ""             # generic fallback key
    LLM_MODEL: str = ""               # generic fallback model
    LLM_TIMEOUT_SECONDS: float = 8.0

    # --- Gemini-specific (server-side only) ---
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"

    def resolved_llm_key(self, provider: str) -> str:
        """Server-side key resolution per provider. Never logged, never returned."""
        p = (provider or "").lower()
        if p == "gemini":
            return self.GEMINI_API_KEY or self.LLM_API_KEY
        return self.LLM_API_KEY

    def resolved_llm_model(self, provider: str) -> str:
        p = (provider or "").lower()
        if p == "gemini":
            return self.GEMINI_MODEL or self.LLM_MODEL or "gemini-2.0-flash"
        return self.LLM_MODEL


settings = Settings()
