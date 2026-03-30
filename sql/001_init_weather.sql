-- ============================================================
-- Weather Prediction App - TimescaleDB Schema
-- Spustenie: psql -h localhost -U postgres -f 001_init_weather.sql
-- ============================================================

-- 1. Vytvorenie databazy
-- (spustit samostatne ak databaza este neexistuje)
-- CREATE DATABASE weather_app;
-- \c weather_app

-- 2. TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ============================================================
-- 3. Hlavna tabulka - hodinove predpovede pocasia
-- ============================================================
CREATE TABLE IF NOT EXISTS weather_forecasts (
    time                    TIMESTAMPTZ      NOT NULL,
    latitude                DOUBLE PRECISION NOT NULL,
    longitude               DOUBLE PRECISION NOT NULL,
    temperature_c           DOUBLE PRECISION,
    feels_like_c            DOUBLE PRECISION,
    humidity_pct            SMALLINT,
    precipitation_mm        DOUBLE PRECISION,
    precipitation_prob_pct  SMALLINT,
    weather_code            SMALLINT,
    weather_description     TEXT,
    wind_speed_kmh          DOUBLE PRECISION,
    wind_direction_deg      SMALLINT,
    pressure_hpa            DOUBLE PRECISION,
    cloud_cover_pct         SMALLINT,
    fetched_at              TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

-- Konverzia na hypertable (particionovanie podla stlpca "time")
SELECT create_hypertable('weather_forecasts', 'time', if_not_exists => TRUE);

-- ============================================================
-- 4. Indexy
-- ============================================================

-- Vyhladavanie predpovede pre konkretnu lokalitu a casovy rozsah
CREATE INDEX IF NOT EXISTS idx_forecasts_location_time
    ON weather_forecasts (latitude, longitude, time DESC);

-- Cache lookup - najdenie posledneho fetchu pre danu lokalitu
CREATE INDEX IF NOT EXISTS idx_forecasts_fetched
    ON weather_forecasts (latitude, longitude, fetched_at DESC);

-- ============================================================
-- 5. Cache log - metadata o tom, kedy sa pre aky den a lokalitu
--    naposledy fetchovali data z Open-Meteo
-- ============================================================
CREATE TABLE IF NOT EXISTS forecast_cache_log (
    id              BIGSERIAL        PRIMARY KEY,
    latitude        DOUBLE PRECISION NOT NULL,
    longitude       DOUBLE PRECISION NOT NULL,
    forecast_date   DATE             NOT NULL,
    fetched_at      TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    source          TEXT             NOT NULL DEFAULT 'open-meteo',
    UNIQUE (latitude, longitude, forecast_date)
);

-- ============================================================
-- 6. Retention policy - automaticke mazanie dat starsich ako 30 dni
-- ============================================================
SELECT add_retention_policy('weather_forecasts', INTERVAL '30 days', if_not_exists => TRUE);

-- ============================================================
-- 7. Pomocne query pre aplikaciu (referencne)
-- ============================================================

-- Cache check: existuje cerstvy zaznam pre danu lokalitu a den?
-- (pouziva sa v forecast_service.py)
--
-- SELECT EXISTS (
--     SELECT 1 FROM forecast_cache_log
--     WHERE latitude = $1
--       AND longitude = $2
--       AND forecast_date = $3
--       AND fetched_at > NOW() - INTERVAL '3 hours'
-- );

-- Nacitanie predpovede pre lokalitu a den:
--
-- SELECT * FROM weather_forecasts
-- WHERE latitude = $1
--   AND longitude = $2
--   AND time >= $3::date
--   AND time < ($3::date + INTERVAL '1 day')
-- ORDER BY time ASC;

-- Upsert do cache logu po fetchnuti novych dat:
--
-- INSERT INTO forecast_cache_log (latitude, longitude, forecast_date, fetched_at)
-- VALUES ($1, $2, $3, NOW())
-- ON CONFLICT (latitude, longitude, forecast_date)
-- DO UPDATE SET fetched_at = NOW();
