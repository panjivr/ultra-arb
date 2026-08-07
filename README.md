# REYOG CAPITAL — Advanced AI Market Intelligence

> **Satu folder, semua yang sudah dibangun.**
> Sistem trading arbitrage multi-market otonom + dashboard Bloomberg-style + edge detection AI + deploy production di VPS.

**Lokasi tunggal:** `C:\Users\Panji\Projects\ultra-arb\`
**Live di:** http://103.31.38.106/ (VPS IDCloudHost — jalan 24/7)
**Lokal dev:** http://localhost:3000

---

## 📁 Struktur Folder (semua di sini)

```
ultra-arb/
├── README.md                  ← anda di sini (master index)
├── arb/                       ← seluruh kode Python
│   ├── config.py              ← env settings (pydantic)
│   ├── infra/                 ← Redis bus, DB layer
│   ├── feeds/                 ← market data feeds (CCXT)
│   ├── strategies/            ← cross-exchange, funding, basis, polymarket
│   ├── models/                ← HMM, cointegration, Bayesian, Kalman
│   ├── risk/                  ← Kelly sizing, circuit breakers
│   ├── execution/             ← paper/live executor
│   ├── edges/                 ← 6 AI edge detectors (lihat di bawah)
│   └── dashboard/
│       ├── api/               ← FastAPI (60+ endpoint REST + WS)
│       └── frontend/          ← Next.js dashboard (28 komponen)
├── scripts/                   ← engine, edge runner, deploy, simulator
│   ├── real_market_engine.py  ← engine utama (ticks + polymarket bets)
│   ├── edge_runner.py         ← 6 edge scanner paralel
│   ├── auto_deploy.py         ← deploy otomatis ke VPS via paramiko
│   └── ...
├── rust/                      ← PyO3 hot paths (Kelly, Kalman, spread)
├── deploy/                    ← Dockerfile, nginx, SSH keys, deploy script
├── docs/                      ← SEMUA dokumentasi
│   ├── 00-original-plan.md    ← rencana awal 8-fase
│   ├── 03-deploy-vps.md       ← panduan deploy VPS umum
│   ├── 04-deploy-idcloudhost.md ← panduan IDCloudHost spesifik
│   └── 05-deposit-guide.md    ← cara deposit real money
├── runtime-logs/              ← semua log (engine, fastapi, deploy)
├── docker-compose.yml         ← 7-service stack
├── Dockerfile.backend         ← FastAPI + engine + edge_runner
├── Dockerfile.frontend        ← Next.js standalone
└── .env.example               ← template environment
```

---

## 🎯 Apa yang Sudah Dibangun (kronologis sesuai prompt anda)

### Fase 1 — Sistem Arbitrage Inti
- Engine event-driven Python 3.12 + Rust PyO3 hot-paths
- Redis Lists message bus, PostgreSQL/TimescaleDB storage
- 4 strategi: cross-exchange, funding-rate, basis, polymarket
- Model: HMM regime, cointegration, Bayesian, Kalman filter
- Risk: Kelly sizing, drawdown/vol circuit breakers
- Paper-trade mode dengan `PAPER_TRADE=true`

### Fase 2 — Dashboard Profesional (13 → 20+ panel)
- StatsBar, EquityChart, StrategyPerformance, PositionsTable
- DetailedSignals (11-faktor), ModelStatus, RiskPanel
- SpreadsMonitor, FundingRates, ActivityMonitor (live pulse)
- ExtendedStats (Sortino/Calmar/Kelly/VaR), HourlyHeatmap
- CorrelationMatrix, EventLog, TickerStream (Bloomberg-style)

### Fase 3 — Harga REAL (bukan demo)
- Ganti hardcoded prices → **Gate.io + HTX public API** live
- BTC/ETH/SOL/BNB/XRP harga real-time tiap detik
- Cross-exchange spread real, ticker badge "● REAL MARKET DATA"

### Fase 4 — Wallet Connect (Polygon)
- Multi-wallet EIP-6963: MetaMask, Phantom, Coinbase, Trust, OKX, Rabby, Brave
- Auto-switch ke Polygon, sign session message
- **Backend auto-refresh balance dari Polygon RPC** (no provider dependency)
- Auto-reconnect, cross-tab sync, balance mismatch detection
- Saldo wallet jadi modal trading (bukan demo $10k)

### Fase 5 — Bloomberg Terminal Intelligence
- **MacroBar**: DXY, Gold, Oil, US10Y, S&P, NASDAQ, VIX, Fear&Greed, BTC dominance
- **NewsTicker**: RSS Cointelegraph/Decrypt/TheBlock/Bitcoin.com (auto HIGH-importance flag)
- **EconomicCalendar**: FOMC/CPI/NFP/crypto events 2026
- **DerivativesPanel**: funding rate + open interest (Gate.io futures)
- **TrendingCoins**, **EquityWatchlist** (financialdatasets.ai)
- **LatencyMonitor**: ns-precision tick→decision pipeline (~77μs)
- WebSocket firehose 100Hz (0ms feel)

### Fase 6 — Polymarket Auto-Betting
- Multi-interval: **5m / 15m / 30m / 1h / 4h / daily**
- Model: Geometric Brownian Motion (range) + momentum (up/down)
- Auto-resolve saat market expire, PnL tracking
- Kelly-sized, scale ke wallet balance
- `PolymarketPanel` + `CompoundingTracker` (projection growth)

### Fase 7 — Edge Detection (hal yang hanya AI bisa)
6 scanner paralel (`scripts/edge_runner.py`):
| Detektor | Edge | Status |
|---|---|---|
| 💎 YES/NO sum arb | Matematika pasti saat harga ≠ $1 | rare |
| 🐋 Smart money copy | Mirror whale trades Polymarket | aktif |
| ⏰ Time decay | Mispricing < 30 menit ke resolve | conditional |
| 🔗 Related markets | Pelanggaran probability ordering | conditional |
| 📰 News reaction | Bet < 15s setelah breaking news | event-driven |
| 💰 Basis carry | Funding APR > 3% delta-neutral | aktif (~9% APR) |
`EdgeRadar` panel — 6-tab live opportunities.

### Fase 8 — Deploy Production VPS
- Docker stack 7-service (nginx/frontend/backend/engine/edge_runner/redis/postgres)
- Deploy otomatis ke **IDCloudHost AlmaLinux** via `scripts/auto_deploy.py`
- nginx reverse proxy, healthcheck semua container
- **Live 24/7 di http://103.31.38.106/**

---

## 🚀 Cara Menjalankan

### Lokal (development)
```bash
cd C:\Users\Panji\Projects\ultra-arb

# Backend
.venv\Scripts\python.exe -m uvicorn arb.dashboard.api.main:app --port 8000

# Engine (ticks + polymarket bets)
.venv\Scripts\python.exe scripts/real_market_engine.py

# Edge scanners
.venv\Scripts\python.exe scripts/edge_runner.py

# Frontend
cd arb/dashboard/frontend && npm run dev
```
Buka http://localhost:3000

### VPS (production — sudah jalan)
```bash
ssh reyogcapital165@103.31.38.106
cd ~/reyog-capital
sudo docker compose ps                  # status
sudo docker compose logs -f engine      # logs
git pull && sudo docker compose up -d --build   # update
```
Buka http://103.31.38.106/

### GRATIS 24/7 (Oracle Cloud Always Free — Rp0, tanpa ubah kode)
```bash
# Di VM Oracle Always Free (Ubuntu ARM/AMD):
git clone https://github.com/panjivr/ultra-arb.git && cd ultra-arb
sudo bash deploy/oracle-setup.sh          # docker + firewall + .env + up
# → http://<PUBLIC_IP>/
```
Pakai domain sendiri (mis. `pusatbanksoal.online`) + HTTPS gratis via Cloudflare:
```bash
sudo DOMAIN=pusatbanksoal.online bash deploy/oracle-setup.sh
```
Panduan: `docs/07-deploy-oracle-gratis.md` (VM) · `docs/08-domain-gratis.md` (domain+HTTPS) · `docs/06-audit-gratisan.md` (audit biaya)

### Re-deploy dari lokal (otomatis)
```bash
.venv\Scripts\python.exe scripts/auto_deploy.py 103.31.38.106 <password> reyogcapital165
```

---

## ⚠️ Disclaimer Penting (jujur)

- **"Pasti profit / 10.000%" TIDAK realistis.** Trader prediction market terbaik di dunia profit 50-200%/tahun.
- Polymarket short-term (5m-1h) **markets-nya efisien** — kompetisi dengan market maker & bot lain.
- Yang **bisa profit konsisten**: math arbitrage (jarang), smart-money copy (lag), basis carry (~9% APR predictable).
- Pure Up/Down betting **statistically ~50/50** + fee/spread = house edge.
- **WAJIB 30 hari paper trading positive expectancy** sebelum `PAPER_TRADE=false`.
- Bot ini memaksimalkan peluang via kecepatan + multi-signal, **bukan jaminan profit**.

---

## 📊 Status Saat Ini

| Metric | Value |
|---|---|
| Mode | PAPER (aman, belum uang asli) |
| VPS | http://103.31.38.106/ — 7/7 container healthy |
| Engine uptime | jalan 24/7 |
| Harga | REAL (Gate.io + HTX) |
| Wallet | siap connect (Polygon, multi-wallet) |
| Edge detectors | 6 aktif |

---

## 🔑 Akses & Kredensial

- **VPS IP**: 103.31.38.106 (IDCloudHost, AlmaLinux 10)
- **VPS user**: reyogcapital165
- **SSH key**: `deploy/deploy_key` (passwordless ke VPS)
- **DB password**: auto-generated, ada di VPS `~/reyog-capital/.env`

Lihat `docs/` untuk panduan lengkap deploy, deposit, dan rencana awal.

---

*Dibangun oleh Claude sebagai REYOG CAPITAL. Semua kode, dokumentasi, log, dan deploy config ada di folder ini — satu sumber kebenaran.*
