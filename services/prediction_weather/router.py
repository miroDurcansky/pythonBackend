from collections import Counter
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query, Depends

from app.auth import check_api_key
from app.services.prediction_weather.database import (
    add_city,
    get_all_cities,
    delete_city,
    fetch_and_save,
    get_forecast_for_day,
    get_forecast_from_now,
    refresh_all_cities,
)

# Router pre servis predpovede pocasia
# Vsetky endpointy budu mat prefix /weather (nastaveny v main.py)
router = APIRouter()


# ---- Mesta ----

@router.post("/cities")
def create_city(
    name: str = Query(),
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    _=Depends(check_api_key),
):
    """Prida mesto a hned stiahne predpovede."""
    city = add_city(name, lat, lon)

    today = date.today()
    tomorrow = today + timedelta(days=1)
    fetch_and_save(city["id"], lat, lon, today)
    fetch_and_save(city["id"], lat, lon, tomorrow)

    return {"message": f"Mesto '{name}' pridane", "city": city}


@router.get("/cities")
def list_cities(_=Depends(check_api_key)):
    return get_all_cities()


@router.delete("/cities/{city_id}")
def remove_city(city_id: int, _=Depends(check_api_key)):
    if not delete_city(city_id):
        raise HTTPException(status_code=404, detail="Mesto nenajdene")
    return {"message": "Mesto zmazane"}


# ---- Predpovede ----

@router.get("/forecast/{city_id}/today")
def forecast_today(city_id: int, _=Depends(check_api_key)):
    """15-minutova predpoved od teraz do konca dna."""
    rows = get_forecast_from_now(city_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Ziadne predpovede pre toto mesto")

    forecast = format_rows(rows)
    return {
        "city_id": city_id,
        "date": date.today().isoformat(),
        "interval_minutes": 15,
        "forecast": forecast,
        "summary": build_summary(forecast),
    }


@router.get("/forecast/{city_id}/tomorrow")
def forecast_tomorrow(city_id: int, _=Depends(check_api_key)):
    """15-minutova predpoved na zajtrajsi den."""
    tomorrow = date.today() + timedelta(days=1)
    rows = get_forecast_for_day(city_id, tomorrow)
    if not rows:
        raise HTTPException(status_code=404, detail="Ziadne predpovede pre toto mesto")

    forecast = format_rows(rows)
    return {
        "city_id": city_id,
        "date": tomorrow.isoformat(),
        "interval_minutes": 15,
        "forecast": forecast,
        "summary": build_summary(forecast),
    }


@router.post("/refresh")
def manual_refresh(_=Depends(check_api_key)):
    """Manualne spustenie refreshu."""
    refresh_all_cities()
    return {"message": "Refresh dokonceny"}


# ---- Pomocne funkcie ----

def format_rows(rows):
    result = []
    for row in rows:
        result.append({
            "time": row["time"].isoformat(),
            "temperature_c": row["temperature_c"],
            "feels_like_c": row["feels_like_c"],
            "humidity_pct": row["humidity_pct"],
            "precipitation_mm": row["precipitation_mm"],
            "weather_code": row["weather_code"],
            "weather_description": row["weather_description"],
            "wind_speed_kmh": row["wind_speed_kmh"],
            "wind_direction_deg": row["wind_direction_deg"],
        })
    return result


def build_summary(forecast):
    temps = [h["temperature_c"] for h in forecast if h["temperature_c"] is not None]
    precips = [h["precipitation_mm"] for h in forecast if h["precipitation_mm"] is not None]
    descriptions = [h["weather_description"] for h in forecast if h["weather_description"] is not None]

    dominant_weather = None
    if descriptions:
        dominant_weather = Counter(descriptions).most_common(1)[0][0]

    return {
        "temp_min_c": min(temps) if temps else None,
        "temp_max_c": max(temps) if temps else None,
        "total_precipitation_mm": round(sum(precips), 2) if precips else None,
        "dominant_weather": dominant_weather,
    }
