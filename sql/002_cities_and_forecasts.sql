-- ============================================================
-- Weather Prediction App v2 - Mesta + 15-min predpovede
-- Spustenie: psql -h localhost -U postgres -f 002_cities_and_forecasts.sql
-- ============================================================

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ============================================================
-- 1. Tabulka miest s GPS suradnicami
-- ============================================================
CREATE TABLE IF NOT EXISTS cities (
    id          SERIAL          PRIMARY KEY,
    name        TEXT            NOT NULL UNIQUE,
    latitude    DOUBLE PRECISION NOT NULL,
    longitude   DOUBLE PRECISION NOT NULL,
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 2. 15-minutove predpovede pre mesta (dnesok + zajtrajsok)
-- ============================================================
CREATE TABLE IF NOT EXISTS forecasts_15min (
    time                TIMESTAMPTZ      NOT NULL,
    city_id             INTEGER          NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
    temperature_c       DOUBLE PRECISION,
    feels_like_c        DOUBLE PRECISION,
    humidity_pct        SMALLINT,
    precipitation_mm    DOUBLE PRECISION,
    weather_code        SMALLINT,
    weather_description TEXT,
    wind_speed_kmh      DOUBLE PRECISION,
    wind_direction_deg  SMALLINT,
    fetched_at          TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

SELECT create_hypertable('forecasts_15min', 'time', if_not_exists => TRUE);

-- Index pre vyhladavanie podla mesta a casu
CREATE INDEX IF NOT EXISTS idx_forecasts_15min_city_time
    ON forecasts_15min (city_id, time DESC);

-- Retention policy - ZRUSENA, ponechavame historicke data
-- SELECT add_retention_policy('forecasts_15min', INTERVAL '7 days', if_not_exists => TRUE);
