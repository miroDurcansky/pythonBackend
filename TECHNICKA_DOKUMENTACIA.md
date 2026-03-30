# Technicka dokumentacia - zdrojovy kod

Tento dokument vysvetluje architekturu a zdrojovy kod multi-servisnej aplikacie.

---

## Architektura

Aplikacia je rozdelena na **servisy**. Kazdy servis je samostatny priecinok v `app/services/` ktory obsahuje vlastne endpointy, databazove funkcie a biznis logiku.

```
app/
├── main.py                          # Hlavna app - spaja vsetko dokopy
├── auth.py                          # Spolocna autentifikacia (API kluc)
└── services/
    ├── prediction_weather/          # Servis 1: Predpoved pocasia
    │   ├── router.py
    │   ├── database.py
    │   ├── scheduler.py
    │   └── weather_codes.py
    ├── solar_forecast/              # Servis 2: Predikcia vyroby FVE
    │   ├── router.py
    │   ├── database.py
    │   └── scheduler.py
    └── math_modeling/               # Servis 3: Matematicke modelovanie
        └── router.py
```

### Preco takato struktura?

Ked je cely kod v jednom `main.py`, tak:
- subor sa stava neprehladny (200+ riadkov)
- dva ludia nemozu pracovat na roznych servisoch bez konfliktov
- nie je jasne co patri k comu

Po refaktoringu:
- kazdy servis je **izolovaný** vo vlastnom priecinku
- novy servis pridame bez toho aby sme menili existujuci kod
- v Swagger UI (`/docs`) su endpointy zoskupene podla servisov

---

## 1. app/main.py - Hlavna aplikacia

```python
from fastapi import FastAPI

from app.services.prediction_weather.router import router as weather_router
from app.services.prediction_weather.scheduler import start_weather_scheduler
from app.services.math_modeling.router import router as math_router
from app.services.solar_forecast.router import router as solar_router
from app.services.solar_forecast.scheduler import start_solar_scheduler
```

Importujeme `router` z kazdeho servisu. Pouzivame aliasy (`as weather_router`, `as solar_router`, `as math_router`) pretoze oba sa volaju `router` - aliasy ich odlisia.

```python
app = FastAPI(title="Multi-Service API", version="2.0.0")
```

Vytvori hlavnu FastAPI instanciu. Toto je jediny `FastAPI()` objekt v celej aplikacii.

```python
app.include_router(weather_router, prefix="/weather", tags=["Predpoved pocasia"])
app.include_router(math_router, prefix="/math", tags=["Matematicke modelovanie"])
app.include_router(solar_router, prefix="/solar", tags=["Predikcia vyroby FVE"])
```

**`include_router()` je klucova funkcia.** Robi dve veci:

1. **`prefix="/weather"`** - vsetky endpointy z `weather_router` dostanu prefix `/weather`. Takze ak je v routeri definovany `@router.get("/cities")`, v aplikacii bude dostupny na `/weather/cities`

2. **`tags=["Predpoved pocasia"]`** - v Swagger UI (`/docs`) sa endpointy zobrazia pod touto hlavicou. Kazdy servis ma svoju sekciu

```python
start_weather_scheduler()
start_solar_scheduler()
```

Spusti background vlakna pre automaticky refresh. Weather kazdych 30 min, solar kazdych 60 min. Volaju sa raz pri starte aplikacie.

```python
@app.get("/health")
def health():
    return {"status": "ok"}
```

Jediny endpoint priamo na hlavnej app (nie v routeri). Nema API kluc ochranu pretoze sluzi na monitoring.

---

## 2. app/auth.py - Spolocna autentifikacia

```python
from fastapi import Header, HTTPException

API_KEY = "5e5944fad25122ffa096ec690f0c547ebdb282342e822b60ba02fae86d3ef3e2"


def check_api_key(x_api_key: str = Header()):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Neplatny API kluc")
```

**Preco je toto v samostatnom subore?** Pretoze ho pouziva viac servisov. Kazdy `router.py` importuje `check_api_key` z tohto jedneho miesta. Ak by sme v buducnosti zmenili sposob autentifikacie (napr. na JWT tokeny), staci zmenit jeden subor.

**Ako funguje `Header()`:**
- FastAPI automaticky cita HTTP hlavicky z requestu
- `x_api_key: str = Header()` hovori: "precitaj hodnotu hlavicky `X-API-Key`"
- FastAPI prevedie nazov parametra `x_api_key` (Python konvencia s podtrznikami) na `X-API-Key` (HTTP konvencia s pomlckami)

**Ako sa pouziva v endpointoch:**
```python
from app.auth import check_api_key

@router.get("/cities")
def list_cities(_=Depends(check_api_key)):
    ...
```

- `Depends(check_api_key)` hovori FastAPI: "pred zavolanim tejto funkcie najprv zavolaj `check_api_key()`"
- Ak `check_api_key` vyhodi `HTTPException`, endpoint sa **nezavola** a klient dostane chybu 401
- `_=` znamena ze vysledok funkcie nepotrebujeme (check_api_key nic nevracia, len kontroluje)

---

## 3. app/services/prediction_weather/ - Servis predpovede pocasia

### router.py - Endpointy

```python
from fastapi import APIRouter, HTTPException, Query, Depends

router = APIRouter()
```

**`APIRouter` vs `FastAPI`:**
- `FastAPI()` sa vytvara len raz v `main.py` - je to hlavna aplikacia
- `APIRouter()` sa vytvara v kazdom servise - je to "skupina endpointov"
- `APIRouter` funguje rovnako ako `FastAPI` - pouzivas `@router.get()`, `@router.post()` atd.
- Rozdiel je ze `APIRouter` nemoze bezat samostatne - musi byt zaregistrovany cez `include_router()`

**Endpointy:**
- `POST /cities` - prida mesto, hned stiahne predpoved na dnes + zajtra
- `GET /cities` - zoznam vsetkych miest
- `DELETE /cities/{id}` - zmaze mesto (CASCADE zmaze aj predpovede)
- `GET /forecast/{id}/today` - predpoved od teraz do konca dna
- `GET /forecast/{id}/tomorrow` - cela zajtrajsia predpoved
- `POST /refresh` - manualne spustenie refreshu vsetkych miest

### scheduler.py - Background refresh

```python
def start_weather_scheduler():
    def loop():
        time.sleep(5)
        while True:
            refresh_all_cities()
            time.sleep(30 * 60)  # 30 minut

    thread = threading.Thread(target=loop)
    thread.daemon = True
    thread.start()
```

**`loop` je funkcia definovana vnútri funkcie** (nested function / closure). Toto je bezny Python pattern. `loop()` existuje len vnútri `start_weather_scheduler()` a nikto zvonku ju nemoze zavolat.

### database.py - DB a API funkcie

Obsahuje vsetky databazove operacie a volania Open-Meteo API. Kazda funkcia si otvori vlastne `psycopg2.connect()` spojenie.

---

## 4. app/services/solar_forecast/ - Servis predikcie vyroby FVE

Tento servis predikuje vyrobu fotovoltaickych elektrarni (FVE) pomocou API **forecast.solar**. Na rozdiel od pocasia, tu su zakaznici (nie mesta) ulozeni v databaze so vsetkymi parametrami FVE.

### Ako funguje forecast.solar API

URL sa sklada z parametrov zakaznika:
```
https://api.forecast.solar/estimate/{lat}/{lon}/{tilt}/{azimuth}/{kwp}
```

- `lat`, `lon` - GPS suradnice
- `tilt` - sklon panelov v stupnoch (0 = horizontalne, 90 = vertikalne)
- `azimuth` - azimut panelov (-180 az 180, 0 = juh, -90 = vychod, 90 = zapad)
- `kwp` - instalovany vykon v kWp

API vrati predikciu na dnes a zajtra s hodinovymi intervalmi:
```json
{
  "result": {
    "watts": {"2026-03-30T07:00:00": 10155, ...},
    "watt_hours_period": {"2026-03-30T07:00:00": 2804, ...},
    "watt_hours": {"2026-03-30T07:00:00": 2804, ...},
    "watt_hours_day": {"2026-03-30": 512876}
  }
}
```

- `watts` - okamzity vykon v danom case (W)
- `watt_hours_period` - energia vyrobena za danu hodinu (Wh)
- `watt_hours` - kumulativna energia od zaciatku dna (Wh)
- `watt_hours_day` - celkova energia za den (Wh)

**Rate limit:** 12 requestov za hodinu na IP adresu (bezplatny plan).

### database.py - DB a API funkcie

```python
FORECAST_SOLAR_BASE = "https://api.forecast.solar/estimate"

def build_api_url(customer):
    return f"{FORECAST_SOLAR_BASE}/{customer['latitude']}/{customer['longitude']}/{customer['tilt_deg']}/{customer['azimuth_deg']}/{customer['kwp']}"
```

**Zakaznici** su ulozeni v tabulke `solar_customers`. Kazdy zakaznik ma vlastne GPS suradnice a parametre panelov. API URL sa sklada dynamicky z tychto udajov.

**Klucove funkcie:**
- `add_customer()` - prida zakaznika (upsert cez `ON CONFLICT`)
- `get_all_customers()` - vrati vsetkych zakaznikov
- `delete_customer()` - zmaze zakaznika (CASCADE zmaze aj predikcie)
- `fetch_and_save_for_customer(customer)` - stiahne predikciu z API pre jedneho zakaznika a ulozi do DB
- `refresh_all_customers()` - zavola `fetch_and_save_for_customer()` pre kazdého zakaznika
- `get_solar_forecast_today(customer_id)` - vrati dnesne zaznamy z DB
- `get_solar_summary_today(customer_id)` - vrati sumarnu statistiku (max W, celkove Wh, sunrise/sunset)

**Upsert logika:**
```python
cursor.execute("""
    INSERT INTO solar_forecasts (time, customer_id, watts, ...)
    VALUES (%s, %s, %s, ...)
    ON CONFLICT (time, customer_id) DO UPDATE SET
        watts = EXCLUDED.watts, ...
""", ...)
```

`ON CONFLICT ... DO UPDATE` znamena: ak zaznam s rovnakym casom a zakaznikom uz existuje, aktualizuj ho novymi hodnotami. Takze pri kazdom fetchi sa predikcie **prepisu** (nie duplikuju).

### router.py - Endpointy

```python
router = APIRouter()
```

**Endpointy:**
- `POST /customers?name=&latitude=&longitude=&tilt_deg=&azimuth_deg=&kwp=` - prida zakaznika, hned stiahne predikciu
- `GET /customers` - zoznam vsetkych zakaznikov
- `DELETE /customers/{id}` - zmaze zakaznika (CASCADE)
- `GET /forecast/{customer_id}/today` - dnesna predikcia vyroby + summary
- `POST /refresh` - manualne spustenie refreshu pre vsetkych zakaznikov

**Odpoved z GET /forecast/{id}/today:**
```json
{
  "customer": {"id": 1, "name": "Trafin Oil", "latitude": 49.80, ...},
  "forecast": [
    {"time": "2026-03-30T07:00:00", "watts": 10155, "watt_hours": 2804, ...},
    ...
  ],
  "summary": {
    "max_watts": 65024,
    "total_watt_hours": 512876,
    "total_kwh": 512.88,
    "sunrise": "...",
    "sunset": "...",
    "last_fetched": "..."
  }
}
```

### scheduler.py - Background refresh

```python
def start_solar_scheduler():
    def loop():
        time.sleep(10)
        while True:
            refresh_all_customers()
            time.sleep(60 * 60)  # 60 minut

    thread = threading.Thread(target=loop)
    thread.daemon = True
    thread.start()
```

Rovnaky pattern ako weather scheduler, ale bezi kazdych **60 minut** (nie 30). Dlhsi interval pretoze:
- forecast.solar ma rate limit 12 req/h
- solarne predikcie sa menia pomalsie ako pocasie

---

## 5. app/services/math_modeling/router.py - Matematicke modelovanie

```python
router = APIRouter()

@router.get("/hello")
def hello(_=Depends(check_api_key)):
    return {
        "service": "math_modeling",
        "message": "Hello World! Tento servis bude v buducnosti rozsireny.",
        "status": "v priprave",
    }
```

Zatial len hello world endpoint. Tento servis bude v buducnosti rozsireny o:
- vlastne `database.py` s DB funkciami pre matematicke modely
- dalsie endpointy v `router.py`
- pripadne `scheduler.py` ak bude potrebovat periodicke vypocty

---

## DB schema

### Tabulky pre pocasie (sql/002_cities_and_forecasts.sql)

```sql
cities (id SERIAL PK, name TEXT UNIQUE, latitude, longitude, created_at)
forecasts_15min (time TIMESTAMPTZ, city_id FK->cities, temperature_c, feels_like_c,
                 humidity_pct, precipitation_mm, weather_code, weather_description,
                 wind_speed_kmh, wind_direction_deg, fetched_at)
-- hypertable, retention 7 dni, index na (city_id, time DESC)
```

### Tabulky pre solar FVE (sql/003 + sql/004)

```sql
solar_customers (id SERIAL PK, name TEXT UNIQUE, latitude, longitude,
                 tilt_deg, azimuth_deg, kwp, created_at)
solar_forecasts (time TIMESTAMPTZ, customer_id FK->solar_customers ON DELETE CASCADE,
                 watts, watt_hours, watt_hours_cumulative, fetched_at,
                 PK(time, customer_id))
-- hypertable, retention 30 dni, index na (customer_id, time DESC)
```

**Preco `solar_customers` ako samostatna tabulka?**
- Parametre FVE (sklon, azimut, vykon) su specificke pre kazdeho zakaznika
- V buducnosti mozno pridat dalsie stlpce (kontaktna osoba, adresa, typ panelov...)
- API URL sa dynamicky sklada z parametrov zakaznika - netreba hardcodovat
- Noveho zakaznika staci pridat cez API a automaticky sa zacne fetchovat

**Preco `ON DELETE CASCADE`?**
- Ked zmazeme zakaznika, automaticky sa zmazu aj jeho predikcie
- Netreba rucne mazat zaznamy z `solar_forecasts`

---

## Ako pridat novy servis (krok za krokom)

Priklad: chceme pridat servis `data_export`:

### Krok 1: Vytvor priecinok a subory

```
app/services/data_export/
├── __init__.py     # prazdny subor
└── router.py       # endpointy
```

### Krok 2: Napís router.py

```python
from fastapi import APIRouter, Depends
from app.auth import check_api_key

router = APIRouter()

@router.get("/csv")
def export_csv(_=Depends(check_api_key)):
    return {"format": "csv", "data": "..."}
```

### Krok 3: Zaregistruj v main.py

Pridaj 2 riadky:

```python
from app.services.data_export.router import router as export_router
app.include_router(export_router, prefix="/export", tags=["Export dat"])
```

Hotovo. Novy endpoint je dostupny na `/export/csv`.

---

## Tok requestu cez aplikaciu

```
Klient posle: GET /solar/forecast/1/today
                     |
                     v
            ┌─────────────────┐
            │   app/main.py    │   FastAPI prijme request
            │   app = FastAPI()│   Hlada zhodu v registrovanych routeroch
            └────────┬────────┘
                     │  prefix="/solar" sa zhoduje
                     v
   ┌──────────────────────────────────┐
   │ solar_forecast/router.py          │   Hlada endpoint /forecast/{id}/today
   │ @router.get("/forecast/{id}/today")│
   └────────┬─────────────────────────┘
            │  Najprv Depends(check_api_key)
            v
     ┌─────────────┐
     │  app/auth.py │   Overi X-API-Key hlavicku
     └──────┬──────┘
            │  OK? Pokracuj. Zly kluc? 401 a koniec.
            v
   ┌────────────────────────────────┐
   │ solar_forecast/database.py      │   get_customer() + get_solar_forecast_today()
   │ SELECT * FROM solar_customers   │   + get_solar_summary_today()
   │ SELECT * FROM solar_forecasts   │   --> riadky z databazy
   └────────┬───────────────────────┘
            │
            v
   ┌────────────────────────────────┐
   │ solar_forecast/router.py        │   Zostavi JSON odpoved s customer info,
   │ return {...}                    │   forecast a summary
   └────────────────────────────────┘
            │
            v
      Klient dostane JSON
```

---

## Zmeny oproti predchadzajucej verzii

| Co sa zmenilo | Pred | Po |
|---------------|------|----|
| Hlavny subor | `prediction_weather/main.py` (vsetko v jednom) | `app/main.py` (len spaja servisy) |
| Endpointy | `@app.get(...)` v main.py | `@router.get(...)` v kazdom router.py |
| URL format | `/cities`, `/forecast/...` | `/weather/cities`, `/solar/forecast/...` |
| API kluc | Definovany v main.py | Samostatny `app/auth.py` |
| Scheduler | Spusta sa pri importe main.py | Explicitne `start_weather_scheduler()` + `start_solar_scheduler()` |
| Novy servis | Vsetko do main.py | Novy priecinok v services/ |
| Spustenie | `uvicorn prediction_weather.main:app` | `uvicorn app.main:app` |
| Math modeling | Neexistovalo | `app/services/math_modeling/router.py` |
| Solar FVE | Neexistovalo | `app/services/solar_forecast/` - predikcia vyroby pre viacerych zakaznikov |
| Solar zakaznici | Hardcoded URL | Tabulka `solar_customers` s parametrami FVE |

---

## Klucove pojmy pre juniora

### APIRouter
Sposob ako rozdelit FastAPI endpointy do viacerych suborov. Kazdy subor ma svoj `router = APIRouter()` a definuje endpointy cez `@router.get()`. Hlavna app ich spoji cez `include_router()`.

### Prefix
Ked zaregistrujes router s `prefix="/weather"`, vsetky jeho URL dostanu tento prefix. Endpoint `@router.get("/cities")` bude v aplikacii na `/weather/cities`.

### Tags
Parameter `tags=["..."]` v `include_router()` zoskupi endpointy v Swagger UI. Je to len vizualna pomoc - na funkcnost to nema vplyv.

### Depends()
FastAPI mechanizmus na zdielanie logiky medzi endpointmi. `Depends(check_api_key)` znamena "pred tymto endpointom najprv zavolaj check_api_key". Ak check_api_key vyhodi chybu, endpoint sa nezavola.

### Daemon thread
Vlakno oznacene ako `daemon=True` sa automaticky zastavi ked sa skonci hlavny program. Bez tohto by scheduler bezal donekonecna aj po ukonceni servera.

### ON CONFLICT (Upsert)
SQL pattern ktory kombinuje INSERT a UPDATE. Ak zaznam s rovnakym klucom uz existuje, namiesto chyby sa aktualizuje. Pouzivame to v solar_forecasts aby sa predikcie prepisovali pri kazdom refreshi.

### Hypertable
TimescaleDB koncept - obycajna PostgreSQL tabulka optimalizovana pre casove rady. Data su automaticky rozdelene do "chunkov" podla casu, co zrychluje dotazy na rozsahy casov.

### Retention policy
Automaticke mazanie starych dat. `add_retention_policy('solar_forecasts', INTERVAL '30 days')` znamena ze zaznamy starsie ako 30 dni sa automaticky zmazu.
