# =============================================================================
# BACKFILL - jednorazove stiahnutie historickych dat pocasia
# =============================================================================
# Stiahne historicke data pocasia (2025 + 2026 do dnes) pre vsetky mesta.
# Pouziva Open-Meteo Historical API (iny endpoint ako bezna predpoved).
#
# Spustenie:
#   python -m app.services.prediction_weather.backfill
#
# Ako to funguje:
#   - Stiahne hodinove data z API po mesiacoch
#   - Kazdu hodinovu hodnotu rozlozi na 4 zaznamy (15-min intervaly)
#     aby boli kompatibilne s beznou predpovedou
#   - Ak pre dany mesiac a mesto uz existuju data, preskoci ho
# =============================================================================

import requests
import psycopg2
import psycopg2.extras
from datetime import date, datetime, timedelta, timezone

from app.services.prediction_weather.database import get_connection, get_all_cities
from app.services.prediction_weather.weather_codes import WMO_CODES

# Historicke API (iny endpoint ako bezna predpoved)
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


def get_existing_months(cursor, city_id):
    """Vrati set mesiacov (YYYY-MM), pre ktore uz existuju data v DB.

    Pouziva sa na preskocenie mesiacov ktore uz boli stiahnutene.
    Priklad navratovej hodnoty: {"2025-01", "2025-02", "2025-03"}
    """
    cursor.execute(
        """
        SELECT DISTINCT to_char(date_trunc('month', time), 'YYYY-MM') as m
        FROM forecasts_15min
        WHERE city_id = %s AND time >= '2025-01-01' AND time < CURRENT_DATE
        """,
        (city_id,),
    )
    return {row["m"] for row in cursor.fetchall()}


def fetch_historical_month(lat, lon, start_date, end_date):
    """Stiahne hodinove data z Open-Meteo Historical API pre dany rozsah datumov."""
    response = requests.get(ARCHIVE_URL, params={
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                  "precipitation,weathercode,windspeed_10m,winddirection_10m",
        "timezone": "auto",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }, timeout=30)
    response.raise_for_status()
    return response.json()["hourly"]


def generate_months(start_date, end_date):
    """Generuje zoznam (prvy_den, posledny_den) pre kazdy mesiac v rozsahu.

    Priklad: generate_months(2025-01-01, 2025-03-15) vrati:
      (2025-01-01, 2025-01-31)
      (2025-02-01, 2025-02-28)
      (2025-03-01, 2025-03-15)  <- orezany na end_date
    """
    current = start_date.replace(day=1)
    while current <= end_date:
        month_start = current

        # Vypocitaj posledny den mesiaca
        if current.month == 12:
            month_end = date(current.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(current.year, current.month + 1, 1) - timedelta(days=1)

        # Ak posledny den mesiaca presahuje end_date, orezneme
        if month_end > end_date:
            month_end = end_date

        yield month_start, month_end

        # Posun na prvy den nasledujuceho mesiaca
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)


def backfill():
    """Hlavna funkcia - stiahne historicke data pre vsetky mesta."""
    start = date(2025, 1, 1)
    end = date.today() - timedelta(days=1)  # Vcera (dnesok uz pokryva bezna predpoved)
    now = datetime.now(timezone.utc)
    cas = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cities = get_all_cities()
    print(f"[BACKFILL] Start: {cas}")
    print(f"[BACKFILL] Rozsah: {start} az {end}")
    print(f"[BACKFILL] Pocet miest: {len(cities)}")
    print()

    total_inserted = 0

    for city in cities:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Zisti ktore mesiace uz mame, aby sme ich neskahovali znova
        existing = get_existing_months(cursor, city["id"])
        print(f"[BACKFILL] === {city['name']} === (existujuce mesiace: {len(existing)})")

        for month_start, month_end in generate_months(start, end):
            month_key = month_start.strftime("%Y-%m")

            # Preskoc mesiace ktore uz mame
            if month_key in existing:
                print(f"  {city['name']} - {month_key} ... PRESKOCENE (data uz existuju)")
                continue

            # Stiahni data z API
            try:
                data = fetch_historical_month(
                    city["latitude"], city["longitude"], month_start, month_end
                )
            except Exception as e:
                print(f"  {city['name']} - {month_key} ... CHYBA API: {e}")
                continue

            # Vloz do DB - kazdu hodinu rozloz na 4x 15-minutove zaznamy
            # (aby boli kompatibilne s beznou predpovedou ktora je tiez po 15 min)
            count = 0
            for i in range(len(data["time"])):
                code = data["weathercode"][i]
                popis = WMO_CODES.get(code, "Neznamy") if code is not None else None

                hour_time = datetime.fromisoformat(data["time"][i])

                # Rozloz 1 hodinovu hodnotu na 4 zaznamy (0, 15, 30, 45 min)
                for offset_min in [0, 15, 30, 45]:
                    t = hour_time + timedelta(minutes=offset_min)
                    cursor.execute(
                        """
                        INSERT INTO forecasts_15min
                            (time, city_id, temperature_c, feels_like_c, humidity_pct,
                             precipitation_mm, weather_code, weather_description,
                             wind_speed_kmh, wind_direction_deg, fetched_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            t, city["id"],
                            data["temperature_2m"][i],
                            data["apparent_temperature"][i],
                            data["relative_humidity_2m"][i],
                            data["precipitation"][i],
                            code, popis,
                            data["windspeed_10m"][i],
                            data["winddirection_10m"][i],
                            now,
                        ),
                    )
                    count += 1

            conn.commit()
            total_inserted += count
            hours = len(data["time"])
            print(f"  {city['name']} - {month_key} ... {count} zaznamov vlozenych ({hours} hodin x 4)")

        cursor.close()
        conn.close()
        print()

    print(f"[BACKFILL] Hotovo: {len(cities)} miest, {total_inserted} zaznamov celkom")


# Umoznuje spustenie priamo: python -m app.services.prediction_weather.backfill
if __name__ == "__main__":
    backfill()
