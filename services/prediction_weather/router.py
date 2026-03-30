# =============================================================================
# ROUTER - endpointy pre predpoved pocasia
# =============================================================================
# Vsetky endpointy v tomto subore budu mat prefix /weather (nastaveny v main.py).
# Priklad: @router.get("/cities") -> dostupne na /weather/cities
#
# Endpointy:
#   POST /weather/cities          - prida mesto + stiahne predpoved
#   GET  /weather/cities          - zoznam miest
#   DEL  /weather/cities/{id}     - zmaze mesto
#   GET  /weather/forecast/{id}/today    - predpoved od teraz do konca dna
#   GET  /weather/forecast/{id}/tomorrow - predpoved na zajtra
#   POST /weather/refresh         - manualne spustenie refreshu
# =============================================================================

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

# APIRouter = skupina endpointov. Na rozdiel od FastAPI() nemoze bezat
# samostatne - musi byt zaregistrovany v hlavnej app cez include_router()
router = APIRouter()


# =============================================================================
# MESTA - CRUD endpointy
# =============================================================================

@router.post("/cities")
def create_city(
    name: str = Query(),
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    _=Depends(check_api_key),
):
    """Prida mesto a hned stiahne predpovede na dnes a zajtra."""
    city = add_city(name, lat, lon)

    # Hned po pridani stiahni predpovede
    today = date.today()
    tomorrow = today + timedelta(days=1)
    fetch_and_save(city["id"], lat, lon, today)
    fetch_and_save(city["id"], lat, lon, tomorrow)

    return {"message": f"Mesto '{name}' pridane", "city": city}


@router.get("/cities")
def list_cities(_=Depends(check_api_key)):
    """Vrati zoznam vsetkych miest."""
    return get_all_cities()


@router.delete("/cities/{city_id}")
def remove_city(city_id: int, _=Depends(check_api_key)):
    """Zmaze mesto. Predpovede sa zmazu automaticky (CASCADE)."""
    if not delete_city(city_id):
        raise HTTPException(status_code=404, detail="Mesto nenajdene")
    return {"message": "Mesto zmazane"}


# =============================================================================
# PREDPOVEDE - endpointy na citanie dat
# =============================================================================

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
    """Manualne spustenie refreshu pre vsetky mesta."""
    refresh_all_cities()
    return {"message": "Refresh dokonceny"}


# =============================================================================
# POMOCNE FUNKCIE
# =============================================================================

def format_rows(rows):
    """Preformatuje DB riadky na JSON-friendly zoznam slovnikov."""
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
    """Zostavi sumarnu statistiku z predpovede (min/max teplota, zrazky, pocasie).

    Counter(descriptions).most_common(1)[0][0] = najcastejsi popis pocasia.
    Priklad: ak je 50x "Jasno" a 10x "Zamracene", vrati "Jasno".
    """
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
