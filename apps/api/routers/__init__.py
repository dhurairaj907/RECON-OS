"""
RECON OS — Routers Package
"""

from routers.webhooks import router as webhooks_router
from routers.dashboard import router as dashboard_router
from routers.events import router as events_router
from routers.payments import router as payments_router
from routers.customers import router as customers_router
from routers.recovery_cases import router as recovery_cases_router
from routers.audit_logs import router as audit_logs_router
from routers.simulator import router as simulator_router
from routers.health import router as health_router
from routers.intelligence import router as intelligence_router
from routers.actions import router as actions_router
from routers.analytics import router as analytics_router
from routers.policies import router as policies_router
from routers.auth import router as auth_router
from routers.communications import router as communications_router
from routers.users import router as users_router
from routers.ai import router as ai_router
from routers.communication_webhooks import router as communication_webhooks_router

__all__ = [
    "webhooks_router",
    "dashboard_router",
    "events_router",
    "payments_router",
    "customers_router",
    "recovery_cases_router",
    "audit_logs_router",
    "simulator_router",
    "health_router",
    "intelligence_router",
    "actions_router",
    "analytics_router",
    "policies_router",
    "auth_router",
    "communications_router",
    "users_router",
    "ai_router",
    "communication_webhooks_router",
]
