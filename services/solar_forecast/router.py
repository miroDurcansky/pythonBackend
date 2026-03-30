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

# Router pre servis predikcie vyroby FVE
# Vsetky endpointy budu mat prefix /solar (nastaveny v main.py)
router = APIRouter()


# ---- Zakaznici ----

@router.post("/customers")
def create_customer(
    name: str = Query(),
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    tilt_deg: int = Query(ge=0, le=90, default=25),
    azimuth_deg: int = Query(ge=-180, le=180, default=0),
    kwp: float = Query(gt=0),
    _=Depends(check_api_key),
):
    """Prida zakaznika a hned stiahne predikciu."""
    customer = add_customer(name, latitude, longitude, tilt_deg, azimuth_deg, kwp)
    fetch_and_save_for_customer(customer)
    return {"message": f"Zakaznik '{name}' pridany", "customer": customer}


@router.get("/customers")
def list_customers(_=Depends(check_api_key)):
    """Vrati zoznam vsetkych zakaznikov."""
    return get_all_customers()


@router.delete("/customers/{customer_id}")
def remove_customer(customer_id: int, _=Depends(check_api_key)):
    """Zmaze zakaznika a jeho predikcie (CASCADE)."""
    if not delete_customer(customer_id):
        raise HTTPException(status_code=404, detail="Zakaznik nenajdeny")
    return {"message": "Zakaznik zmazany"}


# ---- Predikcie ----

@router.get("/forecast/{customer_id}/today")
def solar_forecast_today(customer_id: int, _=Depends(check_api_key)):
    """Dnesna predikcia vyroby FVE pre zakaznika."""
    customer = get_customer(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Zakaznik nenajdeny")

    rows = get_solar_forecast_today(customer_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Ziadne predikcie pre dnesok")

    forecast = []
    for row in rows:
        forecast.append({
            "time": row["time"].isoformat(),
            "watts": row["watts"],
            "watt_hours": row["watt_hours"],
            "watt_hours_cumulative": row["watt_hours_cumulative"],
        })

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
    """Manualne spustenie refreshu pre vsetkych zakaznikov."""
    refresh_all_customers()
    return {"message": "Solar forecast refresh dokonceny pre vsetkych zakaznikov"}
