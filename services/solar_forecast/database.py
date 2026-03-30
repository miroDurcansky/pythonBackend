# =============================================================================
# DATABAZA + API - servis predikcie vyroby FVE (fotovoltaickej elektrarne)
# =============================================================================
# Obsahuje vsetky databazove operacie a volania Forecast.Solar API.
#
# Struktura:
#   1. Zakaznici (CRUD operacie nad tabulkou solar_customers)
#   2. Kontrola existujucich dat (setrenie API rate limitu)
#   3. Stiahnutie a ulozenie predikcie z Forecast.Solar API
#   4. Nacitanie predikcie z databazy
#   5. Refresh vsetkych zakaznikov
#
# Forecast.Solar API:
#   - Bezplatne, bez API kluca
#   - Rate limit: 12 requestov za hodinu na IP adresu
#   - URL format: /estimate/{lat}/{lon}/{sklon}/{azimut}/{vykon_kwp}
#   - Vracia hodinove predikcie vyroby v W a Wh
# =============================================================================

import requests
import psycopg2
import psycopg2.extras
from datetime import date, datetime, timezone

# ---- Konfiguracia databazy ----
DB_HOST = "localhost"
DB_PORT = 5432
DB_USER = "postgres"
DB_PASSWORD = "1234"
DB_NAME = "postgres"

# ---- Forecast.Solar API ----
# URL sa sklada dynamicky z parametrov zakaznika (lat, lon, sklon, azimut, kwp)
FORECAST_SOLAR_BASE = "https://api.forecast.solar/estimate"


def get_connection():
    """Vytvori a vrati nove spojenie s databazou."""
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname=DB_NAME
    )


# =============================================================================
# 1. ZAKAZNICI - CRUD operacie
# =============================================================================

def add_customer(name, latitude, longitude, tilt_deg, azimuth_deg, kwp):
    """Prida zakaznika do databazy. Ak uz existuje (podla name), aktualizuje parametre.

    Parametre FVE:
      - tilt_deg: sklon panelov v stupnoch (0=horizontalne, 90=vertikalne)
      - azimuth_deg: azimut panelov (-180 az 180, 0=juh, -90=vychod, 90=zapad)
      - kwp: instalovany vykon v kilowatt-peak
    """
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
    """Vrati zoznam vsetkych zakaznikov, zoradene podla nazvu."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("SELECT * FROM solar_customers ORDER BY name")
    customers = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return customers


def get_customer(customer_id):
    """Vrati jedneho zakaznika podla ID, alebo None ak neexistuje."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("SELECT * FROM solar_customers WHERE id = %s", (customer_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_customer(customer_id):
    """Zmaze zakaznika. Vrati True ak sa nieco zmazalo, False ak neexistoval.

    Predikcie sa zmazu automaticky vdaka ON DELETE CASCADE na foreign key.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM solar_customers WHERE id = %s", (customer_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


# =============================================================================
# 2. KONTROLA EXISTUJUCICH DAT
# =============================================================================

def has_forecast_today(customer_id):
    """Skontroluje ci uz existuju zaznamy pre dnesok pre daneho zakaznika.

    Pouziva sa na setrenie API rate limitu - ak uz mame data, netreba volat API znova.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COUNT(*) FROM solar_forecasts
        WHERE customer_id = %s AND time >= CURRENT_DATE AND time < (CURRENT_DATE + INTERVAL '1 day')
        """,
        (customer_id,),
    )
    count = cursor.fetchone()[0]
    conn.close()
    return count > 0


# =============================================================================
# 3. STIAHNUTIE A ULOZENIE PREDIKCIE Z API
# =============================================================================

def build_api_url(customer):
    """Zostavi URL pre Forecast.Solar API z parametrov zakaznika.

    Priklad: https://api.forecast.solar/estimate/49.80/18.49/25/0/260
    Parametre v URL: lat/lon/sklon/azimut/vykon_kwp
    """
    return (f"{FORECAST_SOLAR_BASE}/{customer['latitude']}/{customer['longitude']}/"
            f"{customer['tilt_deg']}/{customer['azimuth_deg']}/{customer['kwp']}")


def fetch_and_save_for_customer(customer, force=False):
    """Stiahne predikciu vyroby FVE pre jedneho zakaznika a ulozi do databazy.

    Postup:
      1. Skontroluje ci uz mame data pre dnesok (ak nie je force)
      2. Zavola Forecast.Solar API
      3. Nacita stare zaznamy z DB pre porovnanie
      4. Vlozi/aktualizuje zaznamy (upsert cez ON CONFLICT)
      5. Vypise zmeny do konzoly

    Parametre:
      customer: slovnik s udajmi zakaznika z DB
      force: ak True, ignoruje existujuce data a stiahne znova (pre manualne /refresh)
    """
    customer_id = customer["id"]
    customer_name = customer["name"]

    # Skontroluj ci uz mame data pre dnesok (ak nie je force)
    # Toto setri API rate limit (12 req/h na bezplatnom plane)
    if not force and has_forecast_today(customer_id):
        cas = datetime.now().strftime("%H:%M:%S")
        print(f"[SOLAR] {cas} | {customer_name} | uz existuju zaznamy pre dnesok, preskakujem API volanie")
        return

    # 1. Stiahni data z Forecast.Solar API
    url = build_api_url(customer)
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()

    # API vracia 3 datasety:
    #   watts: okamzity vykon v danom case (W)
    #   watt_hours_period: energia vyrobena za danu hodinu (Wh)
    #   watt_hours: kumulativna energia od zaciatku dna (Wh)
    watts = data["result"]["watts"]
    watt_hours_period = data["result"]["watt_hours_period"]
    watt_hours = data["result"]["watt_hours"]

    # 2. Nacitaj stare zaznamy z DB pre porovnanie
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

    # API vracia data ako slovnik {timestamp_string: hodnota}
    # Prechadz cez vsetky timestamps z watts (klucovy dataset)
    for timestamp_str, watt_value in watts.items():
        t = datetime.fromisoformat(timestamp_str)

        # Spracuj len dnesne zaznamy (API vracia aj zajtrajsok)
        if t.date() != today:
            continue

        wh_period = watt_hours_period.get(timestamp_str)
        wh_cumulative = watt_hours.get(timestamp_str)

        # ON CONFLICT = ak zaznam s rovnakym (time, customer_id) uz existuje,
        # aktualizuj ho novymi hodnotami namiesto chyby (tzv. "upsert")
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

        # Porovnaj so starymi hodnotami
        old = old_rows.get(t)
        if old is None:
            changed.append((t, watt_value, wh_period, None, None))
        elif old["watts"] != watt_value or old["watt_hours"] != wh_period:
            changed.append((t, watt_value, wh_period, old["watts"], old["watt_hours"]))

    conn.commit()
    conn.close()

    # 4. Vypis zmeny do konzoly (uzitocne pre monitoring)
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


# =============================================================================
# 4. NACITANIE PREDIKCIE Z DATABAZY
# =============================================================================

def get_solar_forecast_today(customer_id):
    """Vrati dnesnu predikciu vyroby FVE pre zakaznika (zoznam hodinovych zaznamov)."""
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
    """Vrati sumarnu statistiku dnesnej predikcie (max vykon, celkova energia, cas vyroby).

    Filtruje len zaznamy kde watts > 0 (t.j. ked slnko svieti):
      - sunrise = prvy cas s nenulovym vykonom
      - sunset = posledny cas s nenulovym vykonom
    """
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


# =============================================================================
# 5. REFRESH VSETKYCH ZAKAZNIKOV
# =============================================================================

def refresh_all_customers(force=False):
    """Stiahne predikcie pre vsetkych zakaznikov.

    Volane z:
      - scheduler.py (automaticky kazdych 60 min, force=False)
        -> preskoci zakaznikov ktori uz maju data pre dnesok
      - router.py POST /solar/refresh (manualne, force=True)
        -> vynuti nove stiahnutie pre vsetkych
    """
    customers = get_all_customers()
    cas = datetime.now().strftime("%H:%M:%S")
    print(f"[SOLAR REFRESH] Spusteny o {cas} pre {len(customers)} zakaznikov (force={force})")

    for customer in customers:
        try:
            fetch_and_save_for_customer(customer, force=force)
        except Exception as e:
            print(f"[SOLAR REFRESH] {customer['name']} - CHYBA: {e}")
