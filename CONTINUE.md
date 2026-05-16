# LANJUTAN — Baca ini di session baru

Semua file ada di SATU folder: `C:\Users\Panji\Projects\ultra-arb\`
Baca `README.md` untuk konteks penuh. Project sudah live di VPS http://103.31.38.106/

## YANG SUDAH SELESAI
- 8 fase: arbitrage engine, dashboard 20+ panel, harga REAL (Gate.io/HTX), Bloomberg intel, Polymarket auto-bet, 6 edge detector, deploy VPS
- Wallet fix SELESAI: backend auto-refresh saldo via Polygon RPC (`arb/dashboard/api/routes/wallet.py`), frontend auto-reconnect + cross-tab (`arb/dashboard/frontend/src/components/WalletConnect.tsx`)

## YANG BELUM (lanjutkan di session baru)
1. **Polymarket-only mode**: di `scripts/real_market_engine.py` main() baris ~670-676, tambah env `POLYMARKET_ONLY=true` → skip `emit_signals()`, `emit_trades()`, `emit_funding()` (spot/perp rugi terus). KEEP `emit_ticks()` (perlu harga), `emit_polymarket_bets()`, `resolve_polymarket_bets()`.
2. **AI ensemble strategy**: `emit_polymarket_bets()` (baris 449-572) — gabungkan multi-signal: model GBM/momentum + smart-money copy (`arb/edges/smart_money.py`) + news sentiment + funding direction. Bet HANYA saat 3+ signal agree. Tambah per-asset hit-rate tracking di Redis.
3. **Daily-loss circuit breaker**: stop betting kalau loss harian > X%.
4. **Deploy ke VPS**: `python scripts/auto_deploy.py 103.31.38.106 <pwd> reyogcapital165`

## VPS ACCESS
- IP: 103.31.38.106, user: reyogcapital165, OS: AlmaLinux 10
- SSH key: `deploy/deploy_key` (passwordless)
- `ssh -i deploy/deploy_key reyogcapital165@103.31.38.106`
- VPS path: `~/reyog-capital/` ; `sudo docker compose ps/logs/up -d --build`

## REALITY CHECK (jujur ke user)
"10000% profit" tidak realistis. Edge nyata: basis carry (~9% APR), math arb (jarang), smart-money copy. Up/Down betting ~50/50 + fee. WAJIB 30 hari paper sebelum live.

## CARA JALANKAN LOKAL
backend: `.venv\Scripts\python.exe -m uvicorn arb.dashboard.api.main:app --port 8000`
engine: `.venv\Scripts\python.exe scripts/real_market_engine.py`
edges: `.venv\Scripts\python.exe scripts/edge_runner.py`
frontend: `cd arb/dashboard/frontend && npm run dev`
