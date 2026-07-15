"""
Generate Data: Dashboard Bursa Komoditi
=========================================
Alur:
1. Tarik data harga historis ASLI dari yfinance (legal, gratis, no API key)
2. Generate data transaksi PIALANG SINTETIS yang proporsional ke volume asli
3. Load semuanya ke SQLite sesuai schema.sql

CATATAN JUJUR: Saya belum bisa test script ini end-to-end karena sandbox
saya nggak punya akses internet ke Yahoo Finance. Jalankan ini di
komputer kamu sendiri, dan kalau ada error import/koneksi, itu wajar
di percobaan pertama - debug seperti biasa, jangan asumsikan kode ini
"pasti benar" cuma karena saya yang buat.

Install dulu: pip install yfinance pandas numpy
"""

import sqlite3
import numpy as np
import pandas as pd
from datetime import datetime

try:
    import yfinance as yf
except ImportError:
    raise SystemExit(
        "yfinance belum terinstall. Jalankan: pip install yfinance pandas numpy"
    )

DB_PATH = "commodity_dashboard.db"

# ------------------------------------------------------------
# KONFIGURASI: Daftar komoditi yang ditarik
# ------------------------------------------------------------
# Ticker yfinance untuk futures. Silakan sesuaikan/tambah sendiri -
# cek simbol yang valid di finance.yahoo.com kalau mau komoditi lain.
COMMODITIES = [
    {"code": "CL=F", "name": "Crude Oil WTI", "category": "Energy", "unit": "barrel", "exchange": "NYMEX"},
    {"code": "GC=F", "name": "Gold", "category": "Metal", "unit": "troy ounce", "exchange": "COMEX"},
    {"code": "ZC=F", "name": "Corn", "category": "Agriculture", "unit": "bushel", "exchange": "CBOT"},
    {"code": "KC=F", "name": "Coffee", "category": "Agriculture", "unit": "lb", "exchange": "ICE"},
    # CATATAN: CPO (Crude Palm Oil) Bursa Malaysia sering nggak stabil
    # tersedia di yfinance. Kalau butuh CPO spesifik, cari ticker "FCPO=F"
    # dan cek manual apakah datanya kosong sebelum dipakai produksi.
]

# Broker sintetis - nama fiktif, JANGAN diganti nama broker asli
BROKERS = [
    {"name": "Nusantara Berjangka", "tier": "Tier 1", "join_year": 2015},
    {"name": "Mahakam Futures", "tier": "Tier 1", "join_year": 2012},
    {"name": "Cakrawala Komoditi", "tier": "Tier 2", "join_year": 2018},
    {"name": "Garuda Trade Partners", "tier": "Tier 2", "join_year": 2019},
    {"name": "Sinergi Pialang Mandiri", "tier": "Tier 3", "join_year": 2021},
    {"name": "Bintang Timur Berjangka", "tier": "Tier 3", "join_year": 2022},
]

START_DATE = "2022-01-01"
END_DATE = datetime.today().strftime("%Y-%m-%d")


def build_dim_date(conn, start, end):
    """Generate tabel kalender dari start sampai end date."""
    dates = pd.date_range(start=start, end=end, freq="D")
    rows = []
    for d in dates:
        rows.append({
            "date_key": int(d.strftime("%Y%m%d")),
            "full_date": d.strftime("%Y-%m-%d"),
            "year": d.year,
            "quarter": (d.month - 1) // 3 + 1,
            "month": d.month,
            "month_name": d.strftime("%B"),
            "day": d.day,
            "day_of_week": d.isoweekday(),
            "day_name": d.strftime("%A"),
            "is_weekend": 1 if d.isoweekday() in (6, 7) else 0,
            "is_trading_day": 0 if d.isoweekday() in (6, 7) else 1,
            # NOTE: is_trading_day belum exclude hari libur bursa (Lebaran, dll)
            # Ini simplifikasi sengaja - kalau mau lebih akurat, tambahkan
            # tabel hari libur terpisah dan JOIN exclude di sini.
        })
    df = pd.DataFrame(rows)
    df.to_sql("dim_date", conn, if_exists="append", index=False)
    print(f"dim_date: {len(df)} baris")


def build_dim_commodity(conn):
    df = pd.DataFrame(COMMODITIES).rename(columns={
        "code": "commodity_code", "name": "commodity_name"
    })
    df.to_sql("dim_commodity", conn, if_exists="append", index=False)
    print(f"dim_commodity: {len(df)} baris")
    return pd.read_sql("SELECT commodity_id, commodity_code FROM dim_commodity", conn)


def build_dim_broker(conn):
    df = pd.DataFrame(BROKERS).rename(columns={"name": "broker_name", "tier": "broker_tier"})
    df.to_sql("dim_broker", conn, if_exists="append", index=False)
    print(f"dim_broker: {len(df)} baris")
    return pd.read_sql("SELECT broker_id, broker_name, broker_tier FROM dim_broker", conn)


def fetch_and_load_market_data(conn, commodity_map):
    """Tarik OHLCV asli dari yfinance untuk tiap komoditi."""
    all_rows = []
    for item in COMMODITIES:
        code = item["code"]
        print(f"Menarik data {code} ({item['name']})...")
        try:
            hist = yf.download(code, start=START_DATE, end=END_DATE, progress=False)
        except Exception as e:
            print(f"  GAGAL menarik {code}: {e}")
            continue

        if hist.empty:
            print(f"  PERINGATAN: data kosong untuk {code}, skip. "
                  f"Cek apakah ticker masih valid di Yahoo Finance.")
            continue

        if isinstance(hist.columns, pd.MultiIndex):
            # yfinance versi baru selalu balikin MultiIndex columns (Price, Ticker)
            # walau cuma satu ticker yang diminta - ratakan ke level pertama.
            hist.columns = hist.columns.get_level_values(0)

        commodity_id = int(commodity_map.loc[
            commodity_map["commodity_code"] == code, "commodity_id"
        ].iloc[0])

        hist = hist.reset_index()
        for _, row in hist.iterrows():
            date_key = int(row["Date"].strftime("%Y%m%d"))
            all_rows.append({
                "date_key": date_key,
                "commodity_id": commodity_id,
                "open_price": float(row["Open"]) if pd.notna(row["Open"]) else None,
                "high_price": float(row["High"]) if pd.notna(row["High"]) else None,
                "low_price": float(row["Low"]) if pd.notna(row["Low"]) else None,
                "close_price": float(row["Close"]),
                "total_volume": int(row["Volume"]) if pd.notna(row["Volume"]) else 0,
            })

    df = pd.DataFrame(all_rows)
    df.to_sql("fact_market_daily", conn, if_exists="append", index=False)
    print(f"fact_market_daily: {len(df)} baris")
    return df


def generate_broker_transactions(conn, market_df, broker_df):
    """
    Distribusikan total_volume harian ke tiap broker secara sintetis.

    Pendekatan: tiap broker punya 'market share dasar' berbeda (Tier 1
    dapat porsi lebih besar), lalu ditambah noise harian pakai distribusi
    Dirichlet supaya proporsinya realistis (variatif tapi selalu total 100%).

    INI DATA SIMULASI - bukan transaksi pialang yang benar-benar terjadi.
    Jangan pernah presentasikan ini seolah data real ke orang lain.
    """
    rng = np.random.default_rng(seed=42)  # seed fixed biar reproducible

    tier_weight = {"Tier 1": 3.0, "Tier 2": 1.5, "Tier 3": 0.7}
    base_weights = np.array([tier_weight[t] for t in broker_df["broker_tier"]])
    base_weights = base_weights / base_weights.sum()

    broker_ids = broker_df["broker_id"].tolist()
    rows = []

    for _, mrow in market_df.iterrows():
        # Dirichlet dengan concentration parameter proporsional ke base_weights
        # Semakin besar alpha, semakin dekat ke base_weights (kurang noise)
        alpha = base_weights * 20
        proportions = rng.dirichlet(alpha)

        total_vol = int(mrow["total_volume"])
        close_price = mrow["close_price"]

        # Bulatkan tiap broker, lalu betulkan selisih pembulatan ke broker
        # terakhir supaya SUM(transaction_volume) selalu persis sama dengan
        # total_volume di fact_market_daily. Tanpa ini, ada selisih 1-2 unit
        # per hari yang bikin dashboard kelihatan tidak konsisten kalau dicek detail.
        tx_volumes = [int(round(total_vol * p)) for p in proportions]
        diff = total_vol - sum(tx_volumes)
        tx_volumes[-1] += diff  # selisih pembulatan diserap broker terakhir

        for broker_id, tx_volume in zip(broker_ids, tx_volumes):
            rows.append({
                "date_key": mrow["date_key"],
                "commodity_id": mrow["commodity_id"],
                "broker_id": int(broker_id),
                "transaction_volume": tx_volume,
                "transaction_value": round(tx_volume * close_price, 2),
            })

    df = pd.DataFrame(rows)
    df.to_sql("fact_broker_transaction", conn, if_exists="append", index=False)
    print(f"fact_broker_transaction: {len(df)} baris")


def main():
    with open("schema.sql", "r") as f:
        schema_sql = f.read()

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(schema_sql)

    build_dim_date(conn, START_DATE, END_DATE)
    commodity_map = build_dim_commodity(conn)
    broker_df = build_dim_broker(conn)
    market_df = fetch_and_load_market_data(conn, commodity_map)

    if market_df.empty:
        print("STOP: Tidak ada data market yang berhasil ditarik. "
              "Cek koneksi internet / validitas ticker sebelum lanjut.")
        return

    generate_broker_transactions(conn, market_df, broker_df)

    conn.commit()
    conn.close()
    print(f"\nSelesai. Database tersimpan di: {DB_PATH}")
    print("Selanjutnya: buka file ini di Power BI (Get Data > SQLite database driver)")
    print("atau export ke CSV per tabel kalau Power BI kamu belum ada SQLite connector.")


if __name__ == "__main__":
    main()
