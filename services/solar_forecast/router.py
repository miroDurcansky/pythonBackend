# =============================================================================
# ROUTER - endpointy pre predikciu vyroby FVE
# =============================================================================
# Vsetky endpointy v tomto subore budu mat prefix /solar (nastaveny v main.py).
#
# Endpointy:
#   POST /solar/customers         - prida zakaznika + stiahne predikciu
#   GET  /solar/customers         - zoznam zakaznikov
#   DEL  /solar/customers/{id}    - zmaze zakaznika
#   GET  /solar/forecast/{id}/today - dnesna predikcia vyroby
#   POST /solar/refresh           - manualne spustenie refreshu (force)
# =============================================================================

from fastapi import APIRouter, HTTPException, Query, Depends

from app.auth import check_api_key
from app.services.solar_forecast.database import (
    add_customer,
    get_all_customers,
    get_customer,
    delete_customer,
    refresh_all_customers,
    fetch_and_save_for_customer,
    get_solar_forecast_today,
    get_solar_summary_today,
)

router = APIRouter()


# =============================================================================
# ZAKAZNICI - CRUD endpointy
# =============================================================================

@router.post("/customers")
def create_customer(
    name: str = Query(),
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    tilt_deg: int = Query(ge=0, le=90, default=25),       # Sklon panelov (25° je typicky)
    azimuth_deg: int = Query(ge=-180, le=180, default=0),  # Azimut (0 = juh)
    kwp: float = Query(gt=0),                              # Instalovany vykon v kWp
    _=Depends(check_api_key),
):
    """Prida zakaznika a hned stiahne predikciu vyroby."""
    customer = add_customer(name, latitude, longitude, tilt_deg, azimuth_deg, kwp)
    fetch_and_save_for_customer(customer)
    return {"message": f"Zakaznik '{name}' pridany", "customer": customer}


@router.get("/customers")
def list_customers(_=Depends(check_api_key)):
    """Vrati zoznam vsetkych zakaznikov s ich parametrami FVE."""
    return get_all_customers()


@router.delete("/customers/{customer_id}")
def remove_customer(customer_id: int, _=Depends(check_api_key)):
    """Zmaze zakaznika. Predikcie sa zmazu automaticky (CASCADE)."""
    if not delete_customer(customer_id):
        raise HTTPException(status_code=404, detail="Zakaznik nenajdeny")
    return {"message": "Zakaznik zmazany"}


# =============================================================================
# PREDIKCIE - endpointy na citanie dat
# =============================================================================

@router.get("/forecast/{customer_id}/today")
def solar_forecast_today(customer_id: int, _=Depends(check_api_key)):
    """Dnesna predikcia vyroby FVE pre zakaznika.

    Vrati:
      - customer: info o zakaznikovi a jeho FVE parametroch
      - forecast: zoznam hodinovych zaznamov (cas, watty, watt-hodiny)
      - summary: sumar (max vykon, celkova energia v kWh, sunrise/sunset)
    """
    # Overime ze zakaznik existuje
    customer = get_customer(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Zakaznik nenajdeny")

    # Nacitame predikcie z DB
    rows = get_solar_forecast_today(customer_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Ziadne predikcie pre dnesok")

    # Preformatujeme DB riadky na JSON-friendly format
    forecast = []
    for row in rows:
        forecast.append({
            "time": row["time"].isoformat(),
            "watts": row["watts"],
            "watt_hours": row["watt_hours"],
            "watt_hours_cumulative": row["watt_hours_cumulative"],
        })

    # Sumar - celkove statistiky za den
    summary = get_solar_summary_today(customer_id)

    return {
        "customer": {
            "id": customer["id"],
            "name": customer["name"],
            "latitude": customer["latitude"],
            "longitude": customer["longitude"],
            "tilt_deg": customer["tilt_deg"],
            "azimuth_deg": customer["azimuth_deg"],
            "kwp": customer["kwp"],
        },
        "forecast": forecast,
        "summary": {
            "max_watts": summary["max_watts"] if summary else None,
            "total_watt_hours": summary["total_watt_hours"] if summary else None,
            "total_kwh": round(summary["total_watt_hours"] / 1000, 2) if summary and summary["total_watt_hours"] else None,
            "sunrise": summary["sunrise"].isoformat() if summary and summary["sunrise"] else None,
            "sunset": summary["sunset"].isoformat() if summary and summary["sunset"] else None,
            "last_fetched": summary["posledny_fetch"].isoformat() if summary and summary["posledny_fetch"] else None,
        },
    }


@router.post("/refresh")
def solar_refresh(_=Depends(check_api_key)):
    """Manualne spustenie refreshu pre vsetkych zakaznikov.

    Pouziva force=True - vynuti nove stiahnutie aj ked data uz existuju.
    Na rozdiel od schedulera ktory preskoci zakaznikov s existujucimi datami.
    """
    refresh_all_customers(force=True)
    return {"message": "Solar forecast refresh dokonceny pre vsetkych zakaznikov"}
