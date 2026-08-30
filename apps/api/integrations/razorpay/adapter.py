"""
RECON OS — Razorpay Adapter  (Phase 3: ACT)  — SERVER-SIDE ONLY

Thin, well-bounded client for the ONE outbound call RECON OS makes in Phase 3:

    POST /v1/payment_links          (Razorpay Payment Links API, TEST MODE)

Uses `httpx` (already a dependency — no `razorpay` SDK). Credentials come from
the existing `config.Settings` (`RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET`) — no
second credential system. The key/secret are used for HTTP Basic auth and are
NEVER logged, returned, or persisted.

Every failure is mapped to a structured `PaymentLinkResult(ok=False, ...)` — the
adapter never raises. If credentials are missing the caller gets
`RAZORPAY_NOT_CONFIGURED` and the rest of RECON OS keeps working.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import httpx

from config import settings

logger = logging.getLogger("recon.integrations.razorpay.adapter")


@dataclass
class PaymentLinkResult:
    ok: bool
    payment_link_id: Optional[str] = None      # plink_xxx
    short_url: Optional[str] = None            # public URL — safe to expose
    status: Optional[str] = None               # created | paid | expired | cancelled
    reference_id: Optional[str] = None
    amount_paise: Optional[int] = None
    currency: Optional[str] = None
    error_code: Optional[str] = None           # RAZORPAY_NOT_CONFIGURED | RAZORPAY_NOT_TEST_KEY |
                                               # RAZORPAY_TIMEOUT | RAZORPAY_RATE_LIMITED |
                                               # RAZORPAY_BAD_REQUEST | RAZORPAY_API_ERROR
    error_message: Optional[str] = None
    normalized: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PaymentLinkStatusResult:
    """Authoritative payment-link state fetched from Razorpay (GET /v1/payment_links/{id})."""
    ok: bool
    payment_link_id: Optional[str] = None
    short_url: Optional[str] = None            # public URL — safe to expose
    status: Optional[str] = None               # created | partially_paid | paid | expired | cancelled
    reference_id: Optional[str] = None
    amount_paise: Optional[int] = None          # expected amount
    amount_paid_paise: Optional[int] = None     # amount actually paid so far
    currency: Optional[str] = None
    payments: list = field(default_factory=list)  # [{payment_id, amount, status, created_at}]
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class RazorpayAdapter:
    """Server-side Razorpay Payment Links client (Test Mode)."""

    def __init__(self) -> None:
        self._key_id = settings.RAZORPAY_KEY_ID or ""
        self._key_secret = settings.RAZORPAY_KEY_SECRET or ""
        self._base = settings.RAZORPAY_API_BASE.rstrip("/")
        self._timeout = float(settings.RAZORPAY_TIMEOUT_SECONDS or 10.0)
        self._test_mode = bool(settings.RAZORPAY_TEST_MODE)

    # -- config introspection (no secrets returned) --------------------------
    def is_configured(self) -> bool:
        return bool(self._key_id and self._key_secret)

    def is_test_key(self) -> bool:
        # Razorpay test keys are prefixed rzp_test_ ; live keys rzp_live_
        return self._key_id.startswith("rzp_test_")

    @property
    def test_mode(self) -> bool:
        return self._test_mode

    @property
    def key_id_masked(self) -> str:
        if not self._key_id:
            return ""
        return self._key_id[:11] + "…"  # e.g. "rzp_test_ab…" — id only, never the secret

    # -- the one outbound action -------------------------------------------
    def create_payment_link(
        self,
        *,
        amount_paise: int,
        currency: str,
        reference_id: str,
        description: str,
        customer_name: Optional[str] = None,
        customer_email: Optional[str] = None,
        customer_contact: Optional[str] = None,
        notes: Optional[Dict[str, str]] = None,
    ) -> PaymentLinkResult:
        if not self.is_configured():
            return PaymentLinkResult(
                ok=False, error_code="RAZORPAY_NOT_CONFIGURED",
                error_message="Razorpay credentials are not configured.",
            )
        if not self._test_mode:
            return PaymentLinkResult(
                ok=False, error_code="RAZORPAY_TEST_MODE_DISABLED",
                error_message="RAZORPAY_TEST_MODE is false — live execution is refused.",
            )
        if not self.is_test_key():
            return PaymentLinkResult(
                ok=False, error_code="RAZORPAY_NOT_TEST_KEY",
                error_message="RAZORPAY_KEY_ID is not a test key (expected rzp_test_*).",
            )

        customer: Dict[str, Any] = {}
        if customer_name:
            customer["name"] = customer_name[:120]
        if customer_email:
            customer["email"] = customer_email[:120]
        if customer_contact:
            customer["contact"] = str(customer_contact)[:20]

        body: Dict[str, Any] = {
            "amount": int(amount_paise),
            "currency": currency,
            "accept_partial": False,
            "reference_id": reference_id,
            "description": description[:2048],
            # RECON creates the link only — it does NOT ask Razorpay to notify
            # the customer (no SMS/email providers in Phase 3 scope).
            "notify": {"sms": False, "email": False},
            "reminder_enable": False,
            "notes": {k: str(v)[:255] for k, v in (notes or {}).items()},
        }
        if customer:
            body["customer"] = customer

        url = f"{self._base}/payment_links"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(url, json=body, auth=(self._key_id, self._key_secret))
        except httpx.TimeoutException:
            logger.warning("Razorpay payment_links request timed out (%ss)", self._timeout)
            return PaymentLinkResult(ok=False, error_code="RAZORPAY_TIMEOUT",
                                     error_message="Razorpay request timed out.")
        except httpx.HTTPError as e:
            logger.warning("Razorpay transport error: %s", type(e).__name__)
            return PaymentLinkResult(ok=False, error_code="RAZORPAY_API_ERROR",
                                     error_message="Razorpay transport error.")

        if resp.status_code == 429:
            logger.warning("Razorpay rate limited (429)")
            return PaymentLinkResult(ok=False, error_code="RAZORPAY_RATE_LIMITED",
                                     error_message="Razorpay rate limited.")

        try:
            payload = resp.json()
        except (ValueError, TypeError):
            payload = {}

        if resp.status_code >= 400:
            desc = ""
            try:
                desc = str(payload.get("error", {}).get("description", ""))[:300]
            except Exception:
                desc = ""
            code = "RAZORPAY_BAD_REQUEST" if resp.status_code < 500 else "RAZORPAY_API_ERROR"
            logger.warning("Razorpay payment_links HTTP %s", resp.status_code)
            return PaymentLinkResult(ok=False, error_code=code,
                                     error_message=desc or f"Razorpay HTTP {resp.status_code}")

        pl_id = payload.get("id")
        if not pl_id:
            return PaymentLinkResult(ok=False, error_code="RAZORPAY_API_ERROR",
                                     error_message="Razorpay response missing payment link id.")

        normalized = {
            "id": pl_id,
            "short_url": payload.get("short_url"),
            "status": payload.get("status"),
            "reference_id": payload.get("reference_id"),
            "amount": payload.get("amount"),
            "currency": payload.get("currency"),
        }
        return PaymentLinkResult(
            ok=True,
            payment_link_id=pl_id,
            short_url=payload.get("short_url"),
            status=payload.get("status"),
            reference_id=payload.get("reference_id"),
            amount_paise=payload.get("amount"),
            currency=payload.get("currency"),
            normalized=normalized,
        )

    # -- authoritative status read (for reconciliation) -------------------
    def get_payment_link(self, payment_link_id: str) -> PaymentLinkStatusResult:
        """
        GET /v1/payment_links/{id} — the authoritative source of truth for whether
        a payment link was actually paid. Used by the reconciliation endpoint so a
        real recovery can be confirmed WITHOUT a public webhook. Never raises.
        """
        if not self.is_configured():
            return PaymentLinkStatusResult(ok=False, error_code="RAZORPAY_NOT_CONFIGURED",
                                           error_message="Razorpay credentials are not configured.")
        if not self._test_mode:
            return PaymentLinkStatusResult(ok=False, error_code="RAZORPAY_TEST_MODE_DISABLED",
                                           error_message="RAZORPAY_TEST_MODE is false.")
        if not self.is_test_key():
            return PaymentLinkStatusResult(ok=False, error_code="RAZORPAY_NOT_TEST_KEY",
                                           error_message="RAZORPAY_KEY_ID is not a test key.")
        if not payment_link_id:
            return PaymentLinkStatusResult(ok=False, error_code="RAZORPAY_BAD_REQUEST",
                                           error_message="Missing payment link id.")

        url = f"{self._base}/payment_links/{payment_link_id}"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(url, auth=(self._key_id, self._key_secret))
        except httpx.TimeoutException:
            logger.warning("Razorpay GET payment_links timed out (%ss)", self._timeout)
            return PaymentLinkStatusResult(ok=False, error_code="RAZORPAY_TIMEOUT",
                                           error_message="Razorpay request timed out.")
        except httpx.HTTPError as e:
            logger.warning("Razorpay GET transport error: %s", type(e).__name__)
            return PaymentLinkStatusResult(ok=False, error_code="RAZORPAY_API_ERROR",
                                           error_message="Razorpay transport error.")

        if resp.status_code == 429:
            return PaymentLinkStatusResult(ok=False, error_code="RAZORPAY_RATE_LIMITED",
                                           error_message="Razorpay rate limited.")
        try:
            payload = resp.json()
        except (ValueError, TypeError):
            payload = {}

        if resp.status_code == 404:
            return PaymentLinkStatusResult(ok=False, error_code="RAZORPAY_NOT_FOUND",
                                           error_message="Payment link not found at Razorpay.")
        if resp.status_code >= 400:
            code = "RAZORPAY_BAD_REQUEST" if resp.status_code < 500 else "RAZORPAY_API_ERROR"
            logger.warning("Razorpay GET payment_links HTTP %s", resp.status_code)
            return PaymentLinkStatusResult(ok=False, error_code=code,
                                           error_message=f"Razorpay HTTP {resp.status_code}")

        payments = []
        for p in (payload.get("payments") or []):
            if isinstance(p, dict):
                payments.append({
                    "payment_id": p.get("payment_id") or p.get("id"),
                    "amount": p.get("amount"),
                    "status": p.get("status"),
                    "created_at": p.get("created_at"),
                })

        return PaymentLinkStatusResult(
            ok=True,
            payment_link_id=payload.get("id") or payment_link_id,
            short_url=payload.get("short_url"),
            status=payload.get("status"),
            reference_id=payload.get("reference_id"),
            amount_paise=payload.get("amount"),
            amount_paid_paise=payload.get("amount_paid"),
            currency=payload.get("currency"),
            payments=payments,
        )

    # -- ambiguity recovery (Phase 4: UNKNOWN payment state) ----------------
    def find_payment_link_by_reference(self, reference_id: str) -> PaymentLinkStatusResult:
        """
        Used ONLY to resolve a CREATE-side timeout, where we never received a
        `payment_link_id` to GET directly. A client-side timeout does not mean
        the request never reached Razorpay — this searches Razorpay's own most
        recent Payment Links for one matching our deterministic `reference_id`,
        so a retry is never issued on a guess. Never raises.

        Scoped to the newest 100 links (Razorpay's default list ordering is
        newest-first) — sufficient for a create that just timed out; this is
        not a general-purpose unbounded search.
        """
        if not self.is_configured():
            return PaymentLinkStatusResult(ok=False, error_code="RAZORPAY_NOT_CONFIGURED",
                                           error_message="Razorpay credentials are not configured.")
        if not self._test_mode:
            return PaymentLinkStatusResult(ok=False, error_code="RAZORPAY_TEST_MODE_DISABLED",
                                           error_message="RAZORPAY_TEST_MODE is false.")
        if not self.is_test_key():
            return PaymentLinkStatusResult(ok=False, error_code="RAZORPAY_NOT_TEST_KEY",
                                           error_message="RAZORPAY_KEY_ID is not a test key.")
        if not reference_id:
            return PaymentLinkStatusResult(ok=False, error_code="RAZORPAY_BAD_REQUEST",
                                           error_message="Missing reference id.")

        url = f"{self._base}/payment_links"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(url, params={"count": 100}, auth=(self._key_id, self._key_secret))
        except httpx.TimeoutException:
            logger.warning("Razorpay verification search timed out (%ss)", self._timeout)
            return PaymentLinkStatusResult(ok=False, error_code="RAZORPAY_TIMEOUT",
                                           error_message="Razorpay verification request timed out.")
        except httpx.HTTPError as e:
            logger.warning("Razorpay verification search transport error: %s", type(e).__name__)
            return PaymentLinkStatusResult(ok=False, error_code="RAZORPAY_API_ERROR",
                                           error_message="Razorpay transport error during verification.")

        if resp.status_code == 429:
            return PaymentLinkStatusResult(ok=False, error_code="RAZORPAY_RATE_LIMITED",
                                           error_message="Razorpay rate limited.")
        try:
            payload = resp.json()
        except (ValueError, TypeError):
            payload = {}

        if resp.status_code >= 400:
            code = "RAZORPAY_BAD_REQUEST" if resp.status_code < 500 else "RAZORPAY_API_ERROR"
            logger.warning("Razorpay verification search HTTP %s", resp.status_code)
            return PaymentLinkStatusResult(ok=False, error_code=code,
                                           error_message=f"Razorpay HTTP {resp.status_code}")

        items = payload.get("items") or []
        match = next((it for it in items if isinstance(it, dict)
                     and it.get("reference_id") == reference_id), None)
        if match is None:
            return PaymentLinkStatusResult(ok=False, error_code="RAZORPAY_NOT_FOUND",
                                           error_message="No payment link found for this "
                                                         "reference id among Razorpay's most "
                                                         "recent 100 links.")

        payments = []
        for p in (match.get("payments") or []):
            if isinstance(p, dict):
                payments.append({
                    "payment_id": p.get("payment_id") or p.get("id"),
                    "amount": p.get("amount"),
                    "status": p.get("status"),
                    "created_at": p.get("created_at"),
                })

        return PaymentLinkStatusResult(
            ok=True,
            payment_link_id=match.get("id"),
            short_url=match.get("short_url"),
            status=match.get("status"),
            reference_id=match.get("reference_id"),
            amount_paise=match.get("amount"),
            amount_paid_paise=match.get("amount_paid"),
            currency=match.get("currency"),
            payments=payments,
        )


def get_razorpay_adapter() -> RazorpayAdapter:
    return RazorpayAdapter()
