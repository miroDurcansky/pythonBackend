# CLAUDE.md - Rychly prehlad projektu

## Co to je
Multi-servisna FastAPI aplikacia. Kazdy servis ma vlastny priecinok, router a URL prefix.
Aktualne servisy:
- **prediction_weather** (`/weather/...`) - predpoved pocasia z Open-Meteo, 15-min intervaly
- **solar_forecast** (`/solar/...`) - predikcia vyroby FVE z forecast.solar, hodinove intervaly, viacero zakaznikov
- **math_modeling** (`/math/...`) - matematicke modelovanie (zatial hello world, bude rozsirene)

## Stack
- **Python** (junior level - sync, bez type hintov, jednoduche patterny)
- **FastAPI** + **uvicorn** na porte 8000
- **psycopg2** (sync DB driver)
- **requests** (sync HTTP)
- **TimescaleDB** (PostgreSQL) na localhost:5432, DB=postgres, user=postgres, password=1234
- **Open-Meteo API** - bezplatne, bez API kluca, `minutely_15` endpoint
- **Forecast.Solar API** - bezplatne, bez API kluca, limit 12 requestov/hodinu/IP

## Struktura suborov
```
app/
├── main.py                     # Hlavna app - spaja servisy cez include_router()
├── auth.py                     # API kluc + check_api_key() - spolocne pre vsetky servisy
│
├── services/
│   ├── prediction_weather/     # SERVIS: Predpoved pocasia
│   │   ├── router.py           # Endpointy (APIRouter, prefix /weather)
│   │   ├── database.py         # DB funkcie + fetch z Open-Meteo
│   │   ├── scheduler.py        # Background refresh kazdych 30 min
│   │   └── weather_codes.py    # WMO dict {int: str}
│   │
│   ├── solar_forecast/         # SERVIS: Predikcia vyroby FVE
│   │   ├── router.py           # Endpointy (APIRouter, prefix /solar)
│   │   ├── database.py         # DB funkcie + fetch z forecast.solar
│   │   └── scheduler.py        # Background refresh kazdych 60 min
│   │
│   └── math_modeling/          # SERVIS: Matematicke modelovanie
│       └── router.py           # Hello world endpoint (APIRouter, prefix /math)
│
requirements.txt                # V roote projektu
sql/002_cities_and_forecasts.sql
sql/003_solar_forecast.sql
sql/004_solar_customers.sql
```

## Ako pridat novy servis
1. Vytvor priecinok `app/services/nazov_servisu/`
2. Vytvor `__init__.py` (prazdny) a `router.py`
3. V `router.py`: `router = APIRouter()` + definuj endpointy s `@router.get(...)` atd.
4. V `app/main.py` pridaj: `from app.services.nazov_servisu.router import router as xxx_router`
5. A: `app.include_router(xxx_router, prefix="/xxx", tags=["Nazov"])`
6. Ak treba scheduler: vytvor `scheduler.py` a zavolaj `start_xxx_scheduler()` v `main.py`

## API kluc
```
X-API-Key: 5e5944fad25122ffa096ec690f0c547ebdb282342e822b60ba02fae86d3ef3e2
```
Definovany v `app/auth.py`. Vsetky endpointy okrem `/health` ho vyzaduju.
Pouzitie: `_=Depends(check_api_key)` ako parameter endpointu.

## API endpointy

### Spolocne
```
GET  /health                              -> bez API kluca
```

### Predpoved pocasia (/weather)
```
POST /weather/cities?name=&lat=&lon=      -> add_city() + fetch_and_save() dnes+zajtra
GET  /weather/cities                      -> get_all_cities()
DEL  /weather/cities/{id}                 -> delete_city() CASCADE
GET  /weather/forecast/{id}/today         -> od NOW() do konca dna, 15-min
GET  /weather/forecast/{id}/tomorrow      -> cely zajtrajsi den, 15-min
POST /weather/refresh                     -> refresh_all_cities() manualne
```

### Predikcia vyroby FVE (/solar)
```
POST /solar/customers?name=&latitude=&longitude=&tilt_deg=&azimuth_deg=&kwp=  -> add_customer() + fetch
GET  /solar/customers                     -> get_all_customers()
DEL  /solar/customers/{id}                -> delete_customer() CASCADE
GET  /solar/forecast/{customer_id}/today  -> dnesna predikcia vyroby + summary
POST /solar/refresh                       -> refresh_all_customers() manualne
```

### Matematicke modelovanie (/math)
```
GET  /math/hello                          -> hello world (bude rozsirene)
```

## DB schema

### Pocasie (sql/002_cities_and_forecasts.sql)
```sql
cities (id SERIAL PK, name TEXT UNIQUE, latitude, longitude, created_at)
forecasts_15min (time TIMESTAMPTZ, city_id FK->cities, temperature_c, feels_like_c,
                 humidity_pct, precipitation_mm, weather_code, weather_description,
                 wind_speed_kmh, wind_direction_deg, fetched_at)
-- forecasts_15min je hypertable, retention 7 dni, index na (city_id, time DESC)
```

### Solar FVE (sql/003_solar_forecast.sql + sql/004_solar_customers.sql)
```sql
solar_customers (id SERIAL PK, name TEXT UNIQUE, latitude, longitude,
                 tilt_deg, azimuth_deg, kwp, created_at)
solar_forecasts (time TIMESTAMPTZ, customer_id FK->solar_customers ON DELETE CASCADE,
                 watts, watt_hours, watt_hours_cumulative, fetched_at,
                 PK(time, customer_id))
-- solar_forecasts je hypertable, retention 30 dni, index na (customer_id, time DESC)
```

**Forecast.Solar API URL sa sklada z parametrov zakaznika:**
```
https://api.forecast.solar/estimate/{lat}/{lon}/{tilt}/{azimuth}/{kwp}
```

## Schedulery
- **Weather**: `app/services/prediction_weather/scheduler.py` - kazdych 30 min, refresh vsetkych miest
- **Solar**: `app/services/solar_forecast/scheduler.py` - kazdych 60 min, refresh vsetkych zakaznikov
- Oba sa volaju z `main.py` pri starte, bezia v daemon threadoch

## Spustenie
```bash
docker start timescaledb
uvicorn app.main:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs
```

## Dolezite detaily
- Kazdy servis ma vlastny `router = APIRouter()` - FastAPI pattern pre modularizaciu
- `app.include_router(router, prefix="/weather")` pridava prefix ku vsetkym URL v routeri
- `tags=["..."]` zoskupuje endpointy v Swagger UI podla servisov
- DB config je hardcoded v database.py (nie env premenne) - junior style
- Kazda DB funkcia si otvara vlastny psycopg2.connect() (nie pool)
- `auth.py` je spolocny modul - importuje ho kazdy router
- Solar servis pouziva `ON CONFLICT ... DO UPDATE` pre upsert predikci
- Forecast.Solar API ma rate limit 12 req/h/IP - pri viacerych zakaznikoch treba sledovat
