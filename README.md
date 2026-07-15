# Dashboard Bursa Komoditi

Dashboard interaktif harga & volume komoditi (Crude Oil, Gold, Corn, Coffee)
dengan tema gelap, dibangun pakai Python (Streamlit + pandas + Plotly) di
atas database SQLite.

## Cara menjalankan

```bash
pip install -r requirements.txt
python generate_data.py      # bikin commodity_dashboard.db (sekali saja / refresh data)
streamlit run dashboard.py   # buka dashboard di http://localhost:8501
```

`generate_data.py` menghasilkan `commodity_dashboard.db` (SQLite) berisi 5
tabel sesuai `schema.sql`. Database ini sudah disertakan di repo supaya
dashboard bisa langsung dijalankan tanpa perlu tarik ulang data dulu.

## Isi dashboard (`dashboard.py`)

- Tren harga + moving average (7/14/30 hari), per komoditi
- Volume transaksi harian
- Ranking pialang berdasarkan volume
- Konsentrasi pasar (HHI) per bulan
- Anomali: volume melonjak vs harga stagnan

Filter komoditi & rentang tanggal ada di sidebar.

## Yang sudah divalidasi (end-to-end, dengan akses internet)

- `schema.sql` — dieksekusi tanpa error, semua tabel/index kebentuk.
- `generate_data.py` — dijalankan penuh sampai `commodity_dashboard.db`
  terisi: 1656 baris `dim_date`, 4544 baris `fact_market_daily` (data
  riil dari yfinance untuk CL=F, GC=F, ZC=F, KC=F), 27264 baris
  `fact_broker_transaction`. Total volume broker per hari cocok persis
  dengan `total_volume` di `fact_market_daily`.
- **Bug ditemukan & diperbaiki**: `yf.download()` versi terbaru selalu
  mengembalikan kolom `MultiIndex` (Price, Ticker) walau cuma satu
  ticker yang diminta — ini bikin `row["Open"]` gagal. Sudah difix di
  `fetch_and_load_market_data()` dengan meratakan kolom pakai
  `hist.columns.get_level_values(0)` sebelum diproses.
- Kelima query di `sample_queries.sql` — pola query yang sama dipakai
  ulang di `dashboard.py` (moving average, volatilitas, ranking pialang,
  HHI, anomali volume) dan sudah dites lewat `streamlit.testing.v1.AppTest`
  tanpa exception.
- `dashboard.py` — dijalankan lokal (`streamlit run`), merespons HTTP 200,
  dan lolos `AppTest` (semua chart/metric render, tanpa exception atau
  deprecation warning).

## Langkah selanjutnya (belum saya buatkan, sengaja)

1. **Buka di Power BI**: Get Data > SQLite database driver (perlu install
   ODBC driver SQLite dulu kalau belum ada) > pilih `commodity_dashboard.db`.
2. **Bangun relasi** di Power BI Model view: `dim_date`, `dim_commodity`,
   `dim_broker` ke kedua fact table lewat foreign key masing-masing.
3. **Bikin measure DAX** berdasarkan query di `sample_queries.sql` — jangan
   copy-paste SQL langsung ke DAX, itu bahasa beda. Pakai query SQL ini
   sebagai referensi LOGIKA-nya, lalu terjemahkan ke DAX (ini bagian
   pembelajaran yang saya sebut sebelumnya: DAX row context vs filter
   context).
4. **Desain dashboard interaktif**: minimal ada slicer per komoditi dan
   rentang tanggal, satu visual trend harga + moving average, satu
   visual ranking broker, satu visual HHI/konsentrasi pasar.

Saya sengaja tidak buatkan langkah Power BI-nya karena itu bagian yang
harus kamu kerjakan sendiri untuk benar-benar belajar DAX dan desain
dashboard interaktif — kalau saya buatkan semuanya, kamu cuma akan
paham SQL-nya tapi nggak dapat repetisi yang dibutuhkan untuk kuasai
Power BI.

## Deploy supaya bisa diakses publik (gratis)

Repo ini publik di GitHub, jadi kodenya sudah bisa diakses siapa saja.
Untuk dapat **URL dashboard yang live** (bukan cuma kode), pakai
Streamlit Community Cloud — gratis, tanpa perlu server sendiri:

1. Buka [share.streamlit.io](https://share.streamlit.io) dan login pakai
   akun GitHub kamu (akun yang sama dengan yang dipakai push repo ini).
2. Klik **New app** > pilih repo ini > branch `main` > main file path
   `dashboard.py`.
3. Klik **Deploy**. Dalam 1-2 menit kamu dapat URL publik bentuk
   `https://<nama-app>.streamlit.app` yang bisa dibagikan ke siapa saja.
4. Database `commodity_dashboard.db` sudah ikut ter-commit di repo, jadi
   app langsung jalan tanpa setup tambahan. Kalau mau data harga
   ter-update, jalankan ulang `python generate_data.py` di lokal, commit,
   push — Streamlit Cloud otomatis redeploy.
