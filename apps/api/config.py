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

    # Webhook signature: RECON rejects every inbound webhook unless it carries a
    # valid HMAC-SHA256 signature verified against RAZORPAY_WEBHOOK_SECRET.
    # The only way to accept unsigned webhooks is to opt in explicitly (dev only).
    RAZORPAY_ALLOW_UNSIGNED_WEBHOOKS: bool = False

    # --- Phase 3 (ACT): Simulator ---
    # The simulator is NOT part of the real recovery path. When enabled it is
    # marked simulated=true on every record and audit entry it produces.
    RECON_SIMULATOR_ENABLED: bool = False

    # --- Application ---
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]
    DEFAULT_MERCHANT_NAME: str = "RECON Demo Merchant"

    # --- Phase 4 (PROVE): minimal protection for financial action endpoints ---
    # See security.py. Empty by default (open, for local dev/demo); set to a
    # real shared secret before exposing the API beyond localhost.
    RECON_API_KEY: str = ""
    RECON_RATE_LIMIT_PER_MINUTE: int = 30

    # --- Phase 5: Identity + RBAC ---
    DEFAULT_ORGANIZATION_NAME: str = "RECON Demo Organization"
    SESSION_EXPIRY_HOURS: int = 24
    PASSWORD_RESET_TOKEN_EXPIRY_MINUTES: int = 30
    SESSION_COOKIE_NAME: str = "recon_session"
    # Cookie Secure flag — only safe to enable once served over HTTPS.
    SESSION_COOKIE_SECURE: bool = False
    # Local-dev-only deterministic admin seed (never touches production unless
    # explicitly enabled). Creates one real, properly hashed-password user —
    # not a bypass of authentication.
    RECON_DEV_SEED_ADMIN: bool = False
    RECON_DEV_ADMIN_EMAIL: str = "admin@recon.test"
    RECON_DEV_ADMIN_PASSWORD: str = ""

    # --- Phase 5: Recovery Communications ---
    # "fake" (default, safe for dev/test — never claims real delivery) or
    # "real" (uses the env-configured provider credentials/webhooks below).
    RECON_COMMUNICATIONS_MODE: str = "fake"
    COMMUNICATION_RATE_LIMIT_PER_CASE_PER_DAY: int = 5

    # Minimal real-provider config — server-side only, never sent to the
    # frontend. Email uses stdlib smtplib (no new dependency); SMS/WhatsApp
    # use a generic HTTP webhook via the existing httpx dependency, since no
    # vendor-specific SDK is available/authorized in this phase.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    # False (default) = STARTTLS on connect (port 587 convention). True = implicit
    # TLS from the first byte (port 465 convention) — some real providers require one
    # or the other; both are supported so credentials never have to be faked to fit.
    SMTP_USE_SSL: bool = False
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMS_PROVIDER_WEBHOOK_URL: str = ""
    SMS_PROVIDER_API_KEY: str = ""
    WHATSAPP_PROVIDER_WEBHOOK_URL: str = ""
    WHATSAPP_PROVIDER_API_KEY: str = ""
    # Most real WhatsApp Business API providers refuse freeform text outside an
    # open customer session and require a pre-approved template name instead —
    # default to enforcing that rather than silently sending raw text that a
    # real provider would reject anyway.
    WHATSAPP_REQUIRE_TEMPLATE: bool = True
    # "MESSAGE_TYPE=template_name,MESSAGE_TYPE=template_name" — deliberately a
    # simple key=value list (not JSON) since it only ever holds template
    # identifiers, not arbitrary content.
    WHATSAPP_TEMPLATE_IDS: str = ""

    # --- Phase 7: controlled automatic recovery communication ---
    # Off by default — RECON never contacts a customer automatically unless
    # explicitly enabled. Even when on, every send still goes through the same
    # decide_communication()/send_communication() gate a manual send uses.
    AUTOMATIC_COMMUNICATIONS_ENABLED: bool = False
    # Lifetime cap on ALL messages ever sent for one case (distinct from the
    # per-day rate limit above) — bounds the whole sequence, not just its pace.
    MAX_COMMUNICATIONS_PER_CASE: int = 10
    MAX_COMMUNICATIONS_PER_CUSTOMER_PER_DAY: int = 5
    # Minimum spacing between messages in the AUTOMATIC follow-up sequence
    # only (see services/communications/automation.py) — never applied to a
    # manual/operator-triggered send, which an operator explicitly requested.
    MIN_HOURS_BETWEEN_MESSAGES: int = 12

    # --- Phase 7: provider delivery-status webhooks ---
    # A provider's delivery callback may only ever move a message SENT ->
    # DELIVERED — it can never fabricate an initial send. Rejected unless
    # signed, exactly like the Razorpay webhook, unless explicitly opted into
    # unsigned acceptance for local dev.
    COMMUNICATION_WEBHOOK_SECRET: str = ""
    COMMUNICATION_ALLOW_UNSIGNED_WEBHOOKS: bool = False

    # --- Phase 7: password reset delivery ---
    # Used only to build the reset LINK embedded in the reset email — never
    # sent anywhere itself, never a secret.
    FRONTEND_BASE_URL: str = "http://localhost:3000"
    PASSWORD_RESET_RATE_LIMIT_PER_HOUR: int = 5

    def resolved_whatsapp_template(self, message_type: str) -> str:
        """Server-side only. Returns "" if no template is configured for this
        message type — callers must treat that as NOT_CONFIGURED, never fall
        back to freeform text when WHATSAPP_REQUIRE_TEMPLATE is set."""
        for pair in (self.WHATSAPP_TEMPLATE_IDS or "").split(","):
            if "=" not in pair:
                continue
            key, _, value = pair.partition("=")
            if key.strip().upper() == (message_type or "").upper():
                return value.strip()
        return ""

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
