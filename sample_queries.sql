-- ============================================================
-- QUERY ANALITIS: Basis untuk Dashboard Power BI
-- ============================================================
-- Query-query ini nunjukkin ANALYTICAL THINKING, bukan cuma
-- nampilin data mentah - ini yang dibahas soal beda reporting
-- vs analysis. Masing-masing jawab pertanyaan bisnis spesifik.
-- ============================================================


-- 1. MOVING AVERAGE HARGA (7-hari dan 30-hari)
-- Pertanyaan bisnis: apakah harga sedang trending naik/turun,
-- atau cuma noise harian?
-- Window function: kamu sudah familiar konsep ini dari SQL JOIN/subquery,
-- ini levelnya di atas itu - agregasi dalam "jendela" baris bergerak.
SELECT
    c.commodity_name,
    d.full_date,
    f.close_price,
    AVG(f.close_price) OVER (
        PARTITION BY f.commodity_id
        ORDER BY f.date_key
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS ma_7day,
    AVG(f.close_price) OVER (
        PARTITION BY f.commodity_id
        ORDER BY f.date_key
        ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
    ) AS ma_30day
FROM fact_market_daily f
JOIN dim_commodity c ON f.commodity_id = c.commodity_id
JOIN dim_date d ON f.date_key = d.date_key
ORDER BY c.commodity_name, d.full_date;


-- 2. VOLATILITAS HARIAN (standar deviasi return, rolling 30 hari)
-- Pertanyaan bisnis: komoditi mana yang paling berisiko/fluktuatif
-- akhir-akhir ini? Ini metrik yang nggak native ada di JasperReports
-- biasa - butuh perhitungan statistik.
-- SQLite nggak punya STDEV built-in, jadi dihitung manual pakai
-- rumus varians: AVG((x - mean)^2)
WITH daily_return AS (
    SELECT
        f.commodity_id,
        f.date_key,
        (f.close_price - LAG(f.close_price) OVER (
            PARTITION BY f.commodity_id ORDER BY f.date_key
        )) / LAG(f.close_price) OVER (
            PARTITION BY f.commodity_id ORDER BY f.date_key
        ) AS pct_return
    FROM fact_market_daily f
),
return_with_avg AS (
    SELECT
        commodity_id,
        date_key,
        pct_return,
        AVG(pct_return) OVER (
            PARTITION BY commodity_id ORDER BY date_key
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ) AS avg_return_30d
    FROM daily_return
)
SELECT
    c.commodity_name,
    d.full_date,
    r.pct_return,
    -- volatilitas = akar dari rata-rata kuadrat deviasi (rolling 30 hari)
    SQRT(
        AVG((r.pct_return - r.avg_return_30d) * (r.pct_return - r.avg_return_30d)) OVER (
            PARTITION BY r.commodity_id ORDER BY r.date_key
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        )
    ) AS volatility_30d
FROM return_with_avg r
JOIN dim_commodity c ON r.commodity_id = c.commodity_id
JOIN dim_date d ON r.date_key = d.date_key
WHERE r.pct_return IS NOT NULL
ORDER BY c.commodity_name, d.full_date;


-- 3. RANKING PIALANG PER VOLUME (per komoditi, per bulan)
-- Pertanyaan bisnis: siapa pialang dominan, dan apakah ada konsentrasi
-- risiko di segelintir pialang (relevan buat regulator/risk management)
SELECT
    c.commodity_name,
    d.year,
    d.month,
    b.broker_name,
    b.broker_tier,
    SUM(ft.transaction_volume) AS total_volume,
    RANK() OVER (
        PARTITION BY c.commodity_id, d.year, d.month
        ORDER BY SUM(ft.transaction_volume) DESC
    ) AS rank_in_month
FROM fact_broker_transaction ft
JOIN dim_commodity c ON ft.commodity_id = c.commodity_id
JOIN dim_date d ON ft.date_key = d.date_key
JOIN dim_broker b ON ft.broker_id = b.broker_id
GROUP BY c.commodity_name, d.year, d.month, b.broker_name, b.broker_tier
ORDER BY c.commodity_name, d.year, d.month, rank_in_month;


-- 4. KONSENTRASI PASAR (Herfindahl-Hirschman Index sederhana)
-- Pertanyaan bisnis: seberapa terkonsentrasi transaksi di segelintir
-- pialang besar? HHI tinggi = risiko konsentrasi tinggi.
-- Ini metrik yang dipakai regulator finansial beneran - kalau kamu
-- pakai ini di portofolio dan bisa jelasin, itu sinyal kuat ke interviewer.
WITH monthly_broker_share AS (
    SELECT
        commodity_id,
        strftime('%Y-%m', date(
            substr(CAST(date_key AS TEXT),1,4) || '-' ||
            substr(CAST(date_key AS TEXT),5,2) || '-' ||
            substr(CAST(date_key AS TEXT),7,2)
        )) AS year_month,
        broker_id,
        SUM(transaction_volume) AS broker_volume,
        SUM(SUM(transaction_volume)) OVER (
            PARTITION BY commodity_id, strftime('%Y-%m', date(
                substr(CAST(date_key AS TEXT),1,4) || '-' ||
                substr(CAST(date_key AS TEXT),5,2) || '-' ||
                substr(CAST(date_key AS TEXT),7,2)
            ))
        ) AS total_market_volume
    FROM fact_broker_transaction
    GROUP BY commodity_id, year_month, broker_id
)
SELECT
    c.commodity_name,
    m.year_month,
    -- HHI = jumlah kuadrat market share (dalam persen), max 10000 = monopoli
    SUM((m.broker_volume * 100.0 / m.total_market_volume) *
        (m.broker_volume * 100.0 / m.total_market_volume)) AS hhi_index
FROM monthly_broker_share m
JOIN dim_commodity c ON m.commodity_id = c.commodity_id
GROUP BY c.commodity_name, m.year_month
ORDER BY c.commodity_name, m.year_month;


-- 5. ANOMALI: Volume Melonjak tapi Harga Stagnan
-- Pertanyaan bisnis: kapan ada aktivitas transaksi tinggi tanpa
-- pergerakan harga proporsional? Ini kandidat cerita analisis yang
-- lebih menarik daripada sekadar "harga naik/turun".
WITH volume_zscore AS (
    SELECT
        commodity_id,
        date_key,
        total_volume,
        close_price,
        AVG(total_volume) OVER (
            PARTITION BY commodity_id ORDER BY date_key
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ) AS avg_volume_30d
    FROM fact_market_daily
)
SELECT
    c.commodity_name,
    d.full_date,
    v.total_volume,
    v.avg_volume_30d,
    ROUND(v.total_volume * 1.0 / NULLIF(v.avg_volume_30d, 0), 2) AS volume_ratio,
    v.close_price
FROM volume_zscore v
JOIN dim_commodity c ON v.commodity_id = c.commodity_id
JOIN dim_date d ON v.date_key = d.date_key
WHERE v.total_volume > 1.5 * v.avg_volume_30d  -- threshold: 50% di atas rata-rata
ORDER BY volume_ratio DESC
LIMIT 20;
