import requests
import psycopg2
import psycopg2.extras
from datetime import date, datetime, timezone

# Pripojenie na databazu
DB_HOST = "localhost"
DB_PORT = 5432
DB_USER = "postgres"
DB_PASSWORD = "1234"
DB_NAME = "postgres"

# Forecast.Solar API base URL
FORECAST_SOLAR_BASE = "https://api.forecast.solar/estimate"


def get_connection():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname=DB_NAME
    )


# ---- Zakaznici ----

def add_customer(name, latitude, longitude, tilt_deg, azimuth_deg, kwp):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute(
        """
        INSERT INTO solar_customers (name, latitude, longitude, tilt_deg, azimuth_deg, kwp)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (name) DO UPDATE SET
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            tilt_deg = EXCLUDED.tilt_deg,
            azimuth_deg = EXCLUDED.azimuth_deg,
            kwp = EXCLUDED.kwp
        RETURNING *
        """,
        (name, latitude, longitude, tilt_deg, azimuth_deg, kwp),
    )
    conn.commit()
    customer = dict(cursor.fetchone())
    conn.close()
    return customer


def get_all_customers():
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("SELECT * FROM solar_customers ORDER BY name")
    customers = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return customers


def get_customer(customer_id):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("SELECT * FROM solar_customers WHERE id = %s", (customer_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_customer(customer_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM solar_customers WHERE id = %s", (customer_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


# ---- Stiahnutie a ulozenie predikcie ----

def build_api_url(customer):
    """Zostavi URL pre forecast.solar API z parametrov zakaznika."""
    return f"{FORECAST_SOLAR_BASE}/{customer['latitude']}/{customer['longitude']}/{customer['tilt_deg']}/{customer['azimuth_deg']}/{customer['kwp']}"


def fetch_and_save_for_customer(customer):
    """Stiahne predikciu vyroby FVE pre jedneho zakaznika a ulozi do databazy."""
    customer_id = customer["id"]
    customer_name = customer["name"]

    # 1. Stiahni data z API
    url = build_api_url(customer)
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()

    watts = data["result"]["watts"]
    watt_hours_period = data["result"]["watt_hours_period"]
    watt_hours = data["result"]["watt_hours"]

    # 2. Nacitaj stare zaznamy pre porovnanie
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    today = date.today()
    cursor.execute(
        """
        SELECT time, watts, watt_hours, watt_hours_cumulative
        FROM solar_forecasts
        WHERE customer_id = %s AND time >= %s::date AND time < (%s::date + INTERVAL '1 day')
        ORDER BY time
        """,
        (customer_id, today, today),
    )
    old_rows = {row["time"]: row for row in cursor.fetchall()}

    # 3. Vloz alebo aktualizuj zaznamy pre dnesok
    now = datetime.now(timezone.utc)
    changed = []

    for timestamp_str, watt_value in watts.items():
        t = datetime.fromisoformat(timestamp_str)

        if t.date() != today:
            continue

        wh_period = watt_hours_period.get(timestamp_str)
        wh_cumulative = watt_hours.get(timestamp_str)

        cursor.execute(
            """
            INSERT INTO solar_forecasts (time, customer_id, watts, watt_hours, watt_hours_cumulative, fetched_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (time, customer_id) DO UPDATE SET
                watts = EXCLUDED.watts,
                watt_hours = EXCLUDED.watt_hours,
                watt_hours_cumulative = EXCLUDED.watt_hours_cumulative,
                fetched_at = EXCLUDED.fetched_at
            """,
            (t, customer_id, watt_value, wh_period, wh_cumulative, now),
        )

        old = old_rows.get(t)
        if old is None:
            changed.append((t, watt_value, wh_period, None, None))
        elif old["watts"] != watt_value or old["watt_hours"] != wh_period:
            changed.append((t, watt_value, wh_period, old["watts"], old["watt_hours"]))

    conn.commit()
    conn.close()

    # Vypis zmeny do konzoly
    total_wh_day = data["result"]["watt_hours_day"].get(today.isoformat())
    cas = datetime.now().strftime("%H:%M:%S")

    if changed:
        print(f"[SOLAR] {cas} | {customer_name} | {len(changed)} zmien | denne celkom: {total_wh_day} Wh")
        for t, new_w, new_wh, old_w, old_wh in changed[:5]:
            cas_t = t.strftime("%H:%M")
            if old_w is None:
                print(f"  {cas_t} | NOVY: {new_w} W, {new_wh} Wh")
            else:
                print(f"  {cas_t} | ZMENA: {old_w}->{new_w} W, {old_wh}->{new_wh} Wh")
        if len(changed) > 5:
            print(f"  ... a dalsich {len(changed) - 5} zmien")
    else:
        print(f"[SOLAR] {cas} | {customer_name} | bez zmien | denne celkom: {total_wh_day} Wh")


def refresh_all_customers():
    """Stiahne predikcie pre vsetkych zakaznikov."""
    customers = get_all_customers()
    cas = datetime.now().strftime("%H:%M:%S")
    print(f"[SOLAR REFRESH] Spusteny o {cas} pre {len(customers)} zakaznikov")

    for customer in customers:
        try:
            fetch_and_save_for_customer(customer)
        except Exception as e:
            print(f"[SOLAR REFRESH] {customer['name']} - CHYBA: {e}")


# ---- Nacitanie predikcie z databazy ----

def get_solar_forecast_today(customer_id):
    """Vrati dnesnu predikciu vyroby FVE pre zakaznika."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute(
        """
        SELECT time, watts, watt_hours, watt_hours_cumulative, fetched_at
        FROM solar_forecasts
        WHERE customer_id = %s AND time >= CURRENT_DATE AND time < (CURRENT_DATE + INTERVAL '1 day')
        ORDER BY time
        """,
        (customer_id,),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_solar_summary_today(customer_id):
    """Vrati sumarnu statistiku dnesnej predikcie pre zakaznika."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute(
        """
        SELECT
            COUNT(*) as pocet_zaznamov,
            MAX(watts) as max_watts,
            SUM(watt_hours) as total_watt_hours,
            MIN(time) as sunrise,
            MAX(time) as sunset,
            MAX(fetched_at) as posledny_fetch
        FROM solar_forecasts
        WHERE customer_id = %s AND time >= CURRENT_DATE AND time < (CURRENT_DATE + INTERVAL '1 day')
          AND watts > 0
        """,
        (customer_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None
