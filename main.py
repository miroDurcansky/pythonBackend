from fastapi import FastAPI

from app.services.prediction_weather.router import router as weather_router
from app.services.prediction_weather.scheduler import start_weather_scheduler
from app.services.math_modeling.router import router as math_router
from app.services.solar_forecast.router import router as solar_router
from app.services.solar_forecast.scheduler import start_solar_scheduler

# ---- Hlavna aplikacia ----
# Spaja vsetky servisy dokopy. Kazdy servis ma vlastny router a prefix.

app = FastAPI(title="Multi-Service API", version="2.0.0")

# Registracia servisov - kazdy ma svoj URL prefix a tag pre Swagger UI
app.include_router(weather_router, prefix="/weather", tags=["Predpoved pocasia"])
app.include_router(math_router, prefix="/math", tags=["Matematicke modelovanie"])
app.include_router(solar_router, prefix="/solar", tags=["Predikcia vyroby FVE"])

# Spustenie background schedulerov
start_weather_scheduler()
start_solar_scheduler()


@app.get("/health")
def health():
    """Kontrola ci server bezi. Bez API kluca."""
    return {"status": "ok"}
