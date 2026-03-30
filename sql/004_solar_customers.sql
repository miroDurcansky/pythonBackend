-- Tabulka zakaznikov pre predikciu vyroby FVE
CREATE TABLE IF NOT EXISTS solar_customers (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    latitude    DOUBLE PRECISION NOT NULL,
    longitude   DOUBLE PRECISION NOT NULL,
    tilt_deg    INTEGER NOT NULL DEFAULT 25,
    azimuth_deg INTEGER NOT NULL DEFAULT 0,
    kwp         DOUBLE PRECISION NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Pridaj customer_id do solar_forecasts
ALTER TABLE solar_forecasts ADD COLUMN IF NOT EXISTS customer_id INTEGER REFERENCES solar_customers(id) ON DELETE CASCADE;

-- Zmen PK z (time) na (time, customer_id) aby kazdy zakaznik mal vlastne zaznamy
ALTER TABLE solar_forecasts DROP CONSTRAINT IF EXISTS solar_forecasts_pkey;
ALTER TABLE solar_forecasts ADD PRIMARY KEY (time, customer_id);

-- Index pre dotazy podla zakaznika
CREATE INDEX IF NOT EXISTS idx_solar_forecasts_customer_time ON solar_forecasts (customer_id, time DESC);

-- Vloz Trafin Oil ako prveho zakaznika
INSERT INTO solar_customers (name, latitude, longitude, tilt_deg, azimuth_deg, kwp)
VALUES ('Trafin Oil', 49.80, 18.49, 25, 0, 260)
ON CONFLICT (name) DO NOTHING;
