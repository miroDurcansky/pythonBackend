# =============================================================================
# ROUTER - endpointy pre matematicke modelovanie
# =============================================================================
# Zatial len hello world endpoint. Tento servis bude v buducnosti rozsireny.
#
# Endpointy:
#   GET /math/hello - testovaci endpoint
# =============================================================================

from fastapi import APIRouter, Depends

from app.auth import check_api_key

router = APIRouter()


@router.get("/hello")
def hello(_=Depends(check_api_key)):
    """Hello world endpoint - testuje ze servis funguje."""
    return {
        "service": "math_modeling",
        "message": "Hello World! Tento servis bude v buducnosti rozsireny o matematicke modelovanie.",
        "status": "v priprave",
    }
