"""System platform readiness and GA certification API routes ."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from agentlens.api.auth import AuthContext
from agentlens.api.dependencies import require_auth
from agentlens.readiness.checker import PlatformReadinessChecker

router = APIRouter()
AUTH_DEP = Depends(require_auth)


@router.get("/v1/system/readiness")
async def get_system_readiness(
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    report = PlatformReadinessChecker.run_readiness_audit()

    return JSONResponse(
        status_code=200,
        content={
            "platform_version": report.platform_version,
            "overall_status": report.overall_status,
            "readiness_score": report.readiness_score,
            "total_subsystems": report.total_subsystems,
            "ready_subsystems": report.ready_subsystems,
            "generated_at": report.generated_at.isoformat(),
            "subsystems": [
                {
                    "name": s.name,
                    "is_ready": s.is_ready,
                    "version": s.version,
                    "details": s.details,
                    "checked_at": s.checked_at.isoformat(),
                }
                for s in report.subsystems
            ],
        },
    )


@router.post("/v1/system/certify")
async def certify_platform(
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    cert = PlatformReadinessChecker.generate_certification()

    return JSONResponse(
        status_code=200,
        content={
            "certificate_id": str(cert.certificate_id),
            "platform_version": cert.platform_version,
            "certification_status": cert.certification_status,
            "readiness_score": cert.readiness_score,
            "digital_seal": cert.digital_seal,
            "certified_at": cert.certified_at.isoformat(),
        },
    )
