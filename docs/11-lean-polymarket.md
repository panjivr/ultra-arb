# 11 — Root cause "gabisa dibuka / harus reload" + fix (lean Polymarket)

## Gejala
- Halaman tampil di awal, tapi setelah semua berjalan → **"This page couldn't
  load"**, minta reload terus.
- **Terjadi di 2 host berbeda** (IDCloudHost dan Herza) → bukan jaringan/IP,
  melainkan **aplikasi**.

## Analisis (audit kode)
- Halaman `app/page.tsx` me-mount **~28 komponen** (`ssr:false`), masing-masing
  polling REST via `setInterval` saat halaman dibuka.
- Beberapa endpoint memanggil **API eksternal** dari VPS dan bisa lambat/nge-hang:
  `MacroBar`, `NewsTicker`, `EconomicCalendar`, `DerivativesPanel`,
  `TrendingCoins`, `EquityWatchlist`, `CorrelationMatrix`.
- Efeknya: **~28 request serentak** membanjiri backend kecil (2 uvicorn worker)
  dan menabrak **batas ~6 koneksi/host** di browser. Request lambat menahan
  koneksi → **navigasi/reload berikutnya tak dapat koneksi → "couldn't load"**.
- Reproduksi di host mana pun karena ini beban aplikasi, bukan infrastruktur.
- Firehose/WS **bukan** penyebab: frontend hanya memakai `/ws/live` di
  `SignalFeed`, yang tidak dirender di halaman utama.

## Fix
- **`app/page.tsx` dirampingkan** dari ~28 panel → **9 panel** yang cepat
  (Redis/DB-backed) dan relevan Polymarket:
  Header+Wallet, TickerStream, StatsBar, EquityChart, ActivityMonitor,
  PolymarketPanel, CompoundingTracker, OnChainIntel (whale/smart-money),
  EdgeRadar (copy-trade & arbitrase).
- Dibuang: semua panel Bloomberg/crypto yang memanggil API eksternal + panel
  crypto-trading yang tak dipakai (spreads, funding, heatmap, correlation,
  positions, models, event log, latency, macro, news, calendar, derivatives,
  trending, equities).
- Hasil: koneksi serentak turun drastis → halaman **tetap responsif & reload
  andal**, sekaligus fokus ke Polymarket sesuai tujuan.

## Deploy
```
cd /opt/reyog/ultra-arb && git pull && docker compose -f docker-compose.free.yml up -d --build frontend
```
Uji lewat IP langsung dulu (`http://103.178.153.243/`) untuk memastikan masalah
reload hilang, baru lewat domain/Cloudflare.

## Lanjutan (opsional)
- Kalau ingin lebih ringan lagi: turunkan interval polling per komponen, atau
  gabungkan beberapa endpoint jadi satu.
- Strategi **copy-trade top 1-10 wallet** akan dibangun di atas `smart_money` /
  `poly_intelligence` yang sudah ada.
