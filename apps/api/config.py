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
    # This is a SINGLE, PLATFORM-WIDE credential set — not per-organization.
    # Every organization in this deployment shares the one connected Razorpay
    # account (see database.resolve_connected_merchant). RECON OS has no
    # per-organization encrypted credential store today; a production
    # multi-merchant deployment, where each organization connects its own
    # Razorpay account, needs one before that's safe to build — it was
    # deliberately not improvised in Phase 8 (see the phase report).
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
    # Allowed browser origins for the credentialed session cookie (see
    # main.py's CORSMiddleware). Set to the real deployed frontend origin(s)
    # before a public deployment — see .env.example for the full rationale.
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
    # Cookie SameSite policy — "lax" (default) works for same-site local dev
    # AND a same-site production deployment (frontend + backend sharing a
    # domain, or proxied to appear same-site). A CROSS-SITE deployment
    # (e.g. a Cloudflare Pages frontend calling a separate Render backend
    # domain) needs "none" — browsers refuse to send a Lax/Strict cookie on
    # a cross-site fetch()/XHR at all, which silently breaks every
    # authenticated API call. "none" REQUIRES Secure (auth.py enforces this
    # automatically regardless of SESSION_COOKIE_SECURE — see
    # auth.py::_cookie_attrs) since browsers drop an insecure SameSite=None
    # cookie outright. Valid values: lax | strict | none.
    SESSION_COOKIE_SAMESITE: str = "lax"
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
    # RECON never contacts a customer automatically unless explicitly
    # enabled. Even when on, every send still goes through the same
    # decide_communication()/send_communication() gate a manual send uses.
    # This is one of three flags — together with INTELLIGENCE_ENABLED and
    # AUTOMATIC_ACTION_EXECUTION_ENABLED below — that turn on the fully-
    # automatic DETECT -> RECOVER -> VERIFY chain for real webhook-driven
    # events (Phase 8). All three are True in this deployment's working
    # .env; NEEDS_APPROVAL/REJECTED/UNKNOWN cases remain human-gated
    # regardless of these flags.
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

    # Brevo-specific delivery webhook (POST /webhooks/communications/brevo) —
    # a SEPARATE, additive credential. Brevo's transactional webhooks don't
    # sign the request body the way the generic HMAC path above expects
    # (per developers.brevo.com/docs/secured-webhooks); they authenticate via
    # a static Bearer token configured in Brevo's dashboard instead. Kept as
    # its own setting rather than reusing COMMUNICATION_WEBHOOK_SECRET so the
    # two independent credentials can never be confused or rotated together.
    # There is no "allow unsigned" escape hatch for this one — always fail
    # closed if unset.
    BREVO_WEBHOOK_TOKEN: str = ""

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
    # analyze endpoint works regardless of this flag. This is one of three
    # flags (see AUTOMATIC_COMMUNICATIONS_ENABLED above and
    # AUTOMATIC_ACTION_EXECUTION_ENABLED below) that together turn on the
    # fully-automatic DETECT -> RECOVER -> VERIFY chain for real
    # webhook-driven events (Phase 8).
    INTELLIGENCE_ENABLED: bool = False
    INTELLIGENCE_VERSION: str = "2.5"

    # --- Phase 3 (ACT): automatic execution of Policy-APPROVED actions ---
    # Mirrors AUTOMATIC_COMMUNICATIONS_ENABLED's philosophy exactly, and is
    # the third of the three Phase-8 automation flags described above. When
    # True, run_intelligence() (services/intelligence/
    # orchestrator.py) automatically calls the EXISTING get_or_create_action()
    # + execute_action() right after a fresh analysis concludes with policy
    # verdict APPROVED — no new execution mechanism, no Policy/Action Engine
    # change: execute_action() still independently re-validates policy fresh
    # before ever calling Razorpay, exactly as a manual "execute" click
    # always has. NEEDS_APPROVAL and REJECTED cases are never auto-chained —
    # a human decision remains mandatory for those, unchanged.
    AUTOMATIC_ACTION_EXECUTION_ENABLED: bool = False

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

    # --- NVIDIA NIM-specific (server-side only) ---
    # Works unmodified against either NVIDIA's hosted API catalog
    # (https://integrate.api.nvidia.com/v1, the default) or a self-hosted NIM
    # container (point NVIDIA_NIM_BASE_URL at it) — both expose the same
    # OpenAI-compatible /chat/completions route. No default model: the NIM
    # catalog spans many models with different capabilities/cost, and
    # guessing one would be invented configuration, not a safe default.
    NVIDIA_NIM_API_KEY: str = ""
    NVIDIA_NIM_MODEL: str = ""
    NVIDIA_NIM_BASE_URL: str = "https://integrate.api.nvidia.com/v1"

    def resolved_llm_key(self, provider: str) -> str:
        """Server-side key resolution per provider. Never logged, never returned."""
        p = (provider or "").lower()
        if p == "gemini":
            return self.GEMINI_API_KEY or self.LLM_API_KEY
        if p == "nvidia_nim":
            return self.NVIDIA_NIM_API_KEY or self.LLM_API_KEY
        return self.LLM_API_KEY

    def resolved_llm_model(self, provider: str) -> str:
        p = (provider or "").lower()
        if p == "gemini":
            return self.GEMINI_MODEL or self.LLM_MODEL or "gemini-2.0-flash"
        if p == "nvidia_nim":
            return self.NVIDIA_NIM_MODEL or self.LLM_MODEL
        return self.LLM_MODEL


settings = Settings()
