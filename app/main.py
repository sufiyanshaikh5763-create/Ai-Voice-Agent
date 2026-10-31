"""FastAPI application factory."""
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.routes import (admin, auth, billing, business, contact,
                            email_verification, onboarding, payments, pin,
                            plans)
from app.core.config import get_settings
from app.core.dependencies import SuperAdminUser
from app.core.exceptions import register_exception_handlers
from app.core.middleware import RequestIDMiddleware
from app.core.rate_limit import limiter
from app.services.email_service import warn_if_console_backend_in_production
from app.otp_routes import router as otp_router


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)

    is_docs_active = (settings.app_env != "production") or settings.docs_enabled
    docs_url = "/docs" if is_docs_active else None
    redoc_url = "/redoc" if is_docs_active else None
    openapi_url = "/openapi.json" if is_docs_active else None

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        debug=settings.debug,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )
    
    app.state.limiter = limiter
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(api_router)
    app.include_router(otp_router) 

    # Also mount endpoints at root for callers who omit /api/v1 prefix
    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    app.include_router(pin.router, prefix="/pin", tags=["pin"])
    app.include_router(plans.router, prefix="/plans", tags=["plans"])
    app.include_router(billing.router, prefix="/billing", tags=["billing"])
    app.include_router(business.router, prefix="/business", tags=["business"])
    app.include_router(payments.router, prefix="/payments", tags=["payments"])
    app.include_router(onboarding.router, prefix="/onboarding", tags=["onboarding"])
    app.include_router(email_verification.router, prefix="/auth/verify-email", tags=["auth"])
    app.include_router(admin.router, prefix="/admin", tags=["admin"])
    app.include_router(contact.router, prefix="/contact", tags=["contact"])

    @app.on_event("startup")
    def on_startup() -> None:
        warn_if_console_backend_in_production()
        from app.scripts.seed_super_admins import startup_seed_super_admins
        startup_seed_super_admins()

    @app.get("/openapi.json", include_in_schema=False)
    def root_openapi(request: Request, user: SuperAdminUser):
        return request.app.openapi()

    return app


app = create_app()
