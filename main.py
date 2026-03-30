# =============================================================================
# HLAVNA APLIKACIA - spaja vsetky servisy dokopy
# =============================================================================
# Toto je vstupny bod celej aplikacie. Tu sa vytvara FastAPI instancia
# a registruju sa vsetky servisy (routery) s ich URL prefixami.
#
# Spustenie:  uvicorn app.main:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs
# =============================================================================

from fastapi import FastAPI

# Import routerov z kazdeho servisu
# Kazdy servis ma svoj vlastny "router" (skupina endpointov), preto pouzivame aliasy
from app.services.prediction_weather.router import router as weather_router
from app.services.prediction_weather.scheduler import start_weather_scheduler
from app.services.math_modeling.router import router as math_router
from app.services.solar_forecast.router import router as solar_router
from app.services.solar_forecast.scheduler import start_solar_scheduler

# Vytvorenie hlavnej FastAPI instancie - jedina v celej aplikacii
app = FastAPI(title="Multi-Service API", version="2.0.0")

# Registracia servisov - kazdy router dostane:
#   - prefix: vsetky endpointy v routeri budu mat tento prefix v URL
#   - tags: zoskupenie endpointov v Swagger UI (/docs)
#
# Priklad: ak weather_router ma @router.get("/cities"),
#          po registracii bude dostupny na /weather/cities
app.include_router(weather_router, prefix="/weather", tags=["Predpoved pocasia"])
app.include_router(math_router, prefix="/math", tags=["Matematicke modelovanie"])
app.include_router(solar_router, prefix="/solar", tags=["Predikcia vyroby FVE"])

# Spustenie background schedulerov (bezia v samostatnych vlaknach)
# - weather: kazdych 30 minut stiahne nove predpovede pre vsetky mesta
# - solar: kazdych 60 minut stiahne predikcie pre vsetkych zakaznikov (ak este neexistuju)
start_weather_scheduler()
start_solar_scheduler()


@app.get("/health")
def health():
    """Kontrola ci server bezi. Jediny endpoint bez API kluca."""
    return {"status": "ok"}
