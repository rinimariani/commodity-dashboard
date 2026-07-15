-- ============================================================
-- SKEMA DATABASE: Dashboard Bursa Komoditi
-- Desain: Star Schema (standar untuk BI/dashboard, bukan OLTP)
-- ============================================================
-- CATATAN KRITIS: Ini star schema, BUKAN skema normalisasi 3NF
-- seperti yang mungkin kamu biasa pakai di aplikasi Java/JasperReports.
-- Di dunia BI, kita SENGAJA denormalisasi dimensi supaya query
-- agregasi (SUM, AVG per kategori) jadi cepat dan gampang di-drag-drop
-- ke Power BI tanpa perlu banyak JOIN kompleks di level report.
-- ============================================================

-- DIMENSI: Waktu
-- Dibuat eksplisit (bukan pakai fungsi DATE() on-the-fly) karena
-- Power BI butuh tabel kalender terpisah untuk time intelligence
-- (DAX functions seperti SAMEPERIODLASTYEAR butuh ini)
CREATE TABLE dim_date (
    date_key        INTEGER PRIMARY KEY,  -- format YYYYMMDD, integer supaya sorting cepat
    full_date       DATE NOT NULL,
    year            INTEGER NOT NULL,
    quarter         INTEGER NOT NULL,
    month           INTEGER NOT NULL,
    month_name      TEXT NOT NULL,
    day             INTEGER NOT NULL,
    day_of_week     INTEGER NOT NULL,     -- 1=Senin ... 7=Minggu
    day_name        TEXT NOT NULL,
    is_weekend      INTEGER NOT NULL,     -- 0/1, penting karena bursa tutup weekend
    is_trading_day  INTEGER NOT NULL      -- 0/1, exclude weekend + hari libur bursa
);

-- DIMENSI: Komoditi
CREATE TABLE dim_commodity (
    commodity_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    commodity_code  TEXT NOT NULL UNIQUE,  -- kode ticker (CL=F, GC=F, dll)
    commodity_name  TEXT NOT NULL,
    category        TEXT NOT NULL,          -- Energy, Metal, Agriculture
    unit            TEXT NOT NULL,          -- barrel, troy ounce, metric ton
    exchange        TEXT                    -- NYMEX, COMEX, Bursa Malaysia, dll
);

-- DIMENSI: Pialang
-- PENTING: data ini SINTETIS (lihat generate_data.py), bukan data
-- pialang real. Jangan pernah pakai nama broker asli di sini kalau
-- kamu ambil dari pengalaman kerja lama - lihat diskusi sebelumnya
-- soal risiko data proprietary.
CREATE TABLE dim_broker (
    broker_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    broker_name     TEXT NOT NULL UNIQUE,
    broker_tier     TEXT NOT NULL,   -- Tier 1 (besar), Tier 2 (menengah), Tier 3 (kecil)
    join_year       INTEGER          -- tahun broker mulai aktif, buat analisis kohort
);

-- FACT TABLE 1: Harga & Volume Pasar (agregat harian per komoditi)
-- Ini data ASLI dari yfinance - OHLCV standar.
CREATE TABLE fact_market_daily (
    fact_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    date_key        INTEGER NOT NULL REFERENCES dim_date(date_key),
    commodity_id    INTEGER NOT NULL REFERENCES dim_commodity(commodity_id),
    open_price      REAL,
    high_price      REAL,
    low_price       REAL,
    close_price     REAL NOT NULL,
    total_volume    INTEGER NOT NULL,
    UNIQUE(date_key, commodity_id)
);

-- FACT TABLE 2: Transaksi per Pialang (breakdown sintetis dari total_volume)
-- Total transaction_volume per (date_key, commodity_id) di tabel ini
-- HARUS sama dengan total_volume di fact_market_daily - itu aturan
-- konsistensi yang dijaga oleh generate_data.py.
CREATE TABLE fact_broker_transaction (
    fact_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    date_key            INTEGER NOT NULL REFERENCES dim_date(date_key),
    commodity_id        INTEGER NOT NULL REFERENCES dim_commodity(commodity_id),
    broker_id           INTEGER NOT NULL REFERENCES dim_broker(broker_id),
    transaction_volume  INTEGER NOT NULL,
    transaction_value   REAL NOT NULL   -- volume * closing price hari itu
);

-- Index untuk performa query (kamu akan sering filter/join by date & commodity)
CREATE INDEX idx_market_date ON fact_market_daily(date_key);
CREATE INDEX idx_market_commodity ON fact_market_daily(commodity_id);
CREATE INDEX idx_broker_tx_date ON fact_broker_transaction(date_key);
CREATE INDEX idx_broker_tx_broker ON fact_broker_transaction(broker_id);
