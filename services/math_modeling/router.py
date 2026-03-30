from fastapi import APIRouter, Depends

from app.auth import check_api_key

# Router pre servis matematickeho modelovania
# Vsetky endpointy budu mat prefix /math (nastaveny v main.py)
router = APIRouter()


@router.get("/hello")
def hello(_=Depends(check_api_key)):
    """Hello world endpoint - servis pre matematicke modelovanie."""
    return {
        "service": "math_modeling",
        "message": "Hello World! Tento servis bude v buducnosti rozsireny o matematicke modelovanie.",
        "status": "v priprave",
    }
