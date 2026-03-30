-- Tabulka pre predikciu vyroby FVE z forecast.solar
-- Zakaznik: Trafin Oil (49.80, 18.49, sklon 25°, azimut 0°, 260 kWp)

CREATE TABLE IF NOT EXISTS solar_forecasts (
    time         TIMESTAMPTZ NOT NULL,
    watts        INTEGER,
    watt_hours   INTEGER,
    watt_hours_cumulative INTEGER,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (time)
);

-- Hypertable pre TimescaleDB
SELECT create_hypertable('solar_forecasts', 'time', if_not_exists => TRUE);

-- Retention policy - 30 dni
SELECT add_retention_policy('solar_forecasts', INTERVAL '30 days', if_not_exists => TRUE);

-- Index pre rychle dotazy
CREATE INDEX IF NOT EXISTS idx_solar_forecasts_time ON solar_forecasts (time DESC);
