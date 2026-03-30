import requests
import psycopg2
import psycopg2.extras
from datetime import date, datetime, timedelta, timezone

from app.services.prediction_weather.weather_codes import WMO_CODES

# Pripojenie na databazu
DB_HOST = "localhost"
DB_PORT = 5432
DB_USER = "postgres"
DB_PASSWORD = "1234"
DB_NAME = "postgres"

# Open-Meteo API
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def get_connection():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname=DB_NAME
    )


# ---- Mesta ----

def add_city(name, lat, lon):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute(
        """
        INSERT INTO cities (name, latitude, longitude)
        VALUES (%s, %s, %s)
        ON CONFLICT (name) DO UPDATE SET latitude = %s, longitude = %s
        RETURNING *
        """,
        (name, lat, lon, lat, lon),
    )
    conn.commit()
    city = dict(cursor.fetchone())
    conn.close()
    return city


def get_all_cities():
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("SELECT * FROM cities ORDER BY name")
    cities = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return cities


def delete_city(city_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cities WHERE id = %s", (city_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


# ---- Stiahnutie a ulozenie predpovede ----

def fetch_and_save(city_id, lat, lon, forecast_date, city_name=""):
    """Stiahne 15-min predpoved z Open-Meteo a ulozi do databazy."""

    # 1. Stiahni data z API
    response = requests.get(OPEN_METEO_URL, params={
        "latitude": lat,
        "longitude": lon,
        "minutely_15": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weathercode,windspeed_10m,winddirection_10m",
        "timezone": "auto",
        "start_date": forecast_date.isoformat(),
        "end_date": forecast_date.isoformat(),
    }, timeout=10)
    response.raise_for_status()
    data = response.json()["minutely_15"]

    # 2. Nacitaj stare zaznamy pre porovnanie
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute(
        """
        SELECT time, temperature_c, feels_like_c, humidity_pct, precipitation_mm,
               weather_code, wind_speed_kmh, wind_direction_deg
        FROM forecasts_15min
        WHERE city_id = %s AND time >= %s::date AND time < (%s::date + INTERVAL '1 day')
        ORDER BY time
        """,
        (city_id, forecast_date, forecast_date),
    )
    old_rows = {row["time"]: row for row in cursor.fetchall()}

    # 3. Zmaz stare zaznamy a vloz nove
    cursor.execute(
        "DELETE FROM forecasts_15min WHERE city_id = %s AND time >= %s::date AND time < (%s::date + INTERVAL '1 day')",
        (city_id, forecast_date, forecast_date),
    )

    now = datetime.now(timezone.utc)
    changed = []

    for i in range(len(data["time"])):
        code = data["weathercode"][i]
        if code is not None:
            popis = WMO_CODES.get(code, "Neznamy")
        else:
            popis = None

        t = datetime.fromisoformat(data["time"][i])
        new_vals = {
            "temperature_c": data["temperature_2m"][i],
            "feels_like_c": data["apparent_temperature"][i],
            "humidity_pct": data["relative_humidity_2m"][i],
            "precipitation_mm": data["precipitation"][i],
            "weather_code": code,
            "wind_speed_kmh": data["windspeed_10m"][i],
            "wind_direction_deg": data["winddirection_10m"][i],
        }

        cursor.execute(
            """
            INSERT INTO forecasts_15min
                (time, city_id, temperature_c, feels_like_c, humidity_pct,
                 precipitation_mm, weather_code, weather_description,
                 wind_speed_kmh, wind_direction_deg, fetched_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (t, city_id, new_vals["temperature_c"], new_vals["feels_like_c"],
             new_vals["humidity_pct"], new_vals["precipitation_mm"], code, popis,
             new_vals["wind_speed_kmh"], new_vals["wind_direction_deg"], now),
        )

        # Porovnaj so starymi hodnotami
        old = old_rows.get(t)
        if old is None:
            changed.append((t, new_vals, None, None))
        else:
            diffs = {}
            for key, new_val in new_vals.items():
                old_val = old[key]
                if old_val is not None and new_val is not None:
                    if float(old_val) != float(new_val):
                        diffs[key] = (old_val, new_val)
                elif old_val != new_val:
                    diffs[key] = (old_val, new_val)
            if diffs:
                old_vals = {k: old[k] for k in new_vals}
                changed.append((t, new_vals, diffs, old_vals))

    conn.commit()
    conn.close()

    # Vypis zmeny do konzoly
    if changed:
        label = city_name or f"city_id={city_id}"
        for t, new_vals, diffs, old_vals in changed:
            cas = t.strftime("%H:%M")
            if diffs is None:
                print(f"  {label} | {forecast_date} {cas} | NOVY ZAZNAM")
                print(f"    NOVE:  temp={new_vals['temperature_c']}°C, pocit={new_vals['feels_like_c']}°C, vlhkost={new_vals['humidity_pct']}%, zrazky={new_vals['precipitation_mm']}mm, vietor={new_vals['wind_speed_kmh']}km/h {new_vals['wind_direction_deg']}°")
            else:
                print(f"  {label} | {forecast_date} {cas} | ZMENA")
                print(f"    STARE: temp={old_vals['temperature_c']}°C, pocit={old_vals['feels_like_c']}°C, vlhkost={old_vals['humidity_pct']}%, zrazky={old_vals['precipitation_mm']}mm, vietor={old_vals['wind_speed_kmh']}km/h {old_vals['wind_direction_deg']}°")
                print(f"    NOVE:  temp={new_vals['temperature_c']}°C, pocit={new_vals['feels_like_c']}°C, vlhkost={new_vals['humidity_pct']}%, zrazky={new_vals['precipitation_mm']}mm, vietor={new_vals['wind_speed_kmh']}km/h {new_vals['wind_direction_deg']}°")


# ---- Nacitanie predpovedi z databazy ----

def get_forecast_for_day(city_id, forecast_date):
    """Vrati vsetky 15-min zaznamy pre mesto a dany den."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute(
        """
        SELECT * FROM forecasts_15min
        WHERE city_id = %s AND time >= %s::date AND time < (%s::date + INTERVAL '1 day')
        ORDER BY time
        """,
        (city_id, forecast_date, forecast_date),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_forecast_from_now(city_id):
    """Vrati 15-min zaznamy od teraz do konca dnesneho dna."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute(
        """
        SELECT * FROM forecasts_15min
        WHERE city_id = %s AND time >= NOW() AND time < (CURRENT_DATE + INTERVAL '1 day')
        ORDER BY time
        """,
        (city_id,),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


# ---- Refresh vsetkych miest ----

def refresh_all_cities():
    """Stiahne nove predpovede pre vsetky mesta (dnesok + zajtrajsok)."""
    today = date.today()
    tomorrow = today + timedelta(days=1)
    cas_spustenia = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cities = get_all_cities()
    print(f"[WEATHER REFRESH] Spusteny o {cas_spustenia} pre {len(cities)} miest")

    for city in cities:
        try:
            fetch_and_save(city["id"], city["latitude"], city["longitude"], today, city["name"])
            fetch_and_save(city["id"], city["latitude"], city["longitude"], tomorrow, city["name"])
            print(f"[WEATHER REFRESH] {city['name']} - OK")
        except Exception as e:
            print(f"[WEATHER REFRESH] {city['name']} - CHYBA: {e}")
