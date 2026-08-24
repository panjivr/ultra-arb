# 09 — Web Trading Polymarket (eksekusi + PnL) di hosting GRATIS

> Tujuan Anda: web yang **mengeksekusi di Polymarket** dan **menampilkan flow +
> PnL** di dashboard, dengan hosting **gratis**. Kabar baik: sebagian besar
> **sudah ada** di repo. Dokumen ini merangkai jadi mode "Polymarket-only".

## Apa yang sudah ada (tak perlu bangun dari nol)

| Bagian | File |
|---|---|
| Feed harga Polymarket (Gamma API, 500ms) | `arb/feeds/polymarket_feed.py` |
| Strategi & sinyal Polymarket | `arb/strategies/polymarket_arb.py`, `scripts/real_market_engine.py` |
| Eksekusi PAPER (simulasi, aman) | `real_market_engine.py` (emit_polymarket_bets) |
| Eksekusi LIVE (CLOB, uang asli) | `scripts/polymarket_live_adapter.py` |
| Resolve + akumulasi PnL | `real_market_engine.py` (resolve_polymarket_bets, `arb:poly:resolved`) |
| API dashboard | `routes/polymarket.py`, `pnl.py`, `compounding.py`, `activity.py` |
| Panel web | `PolymarketPanel.tsx`, `PnlChart.tsx`, `CompoundingTracker.tsx`, `EquityChart.tsx` |

Flow di web: **sinyal → bet (paper/live) → tampil di PolymarketPanel → resolve
saat market expire → PnL/equity update di PnlChart + CompoundingTracker**.

## Mode "Polymarket-only"

`oracle-setup.sh` kini men-set otomatis di `.env`:
```
POLYMARKET_ONLY_MODE=true      # engine hanya jalankan strategi Polymarket
CRYPTO_STRATEGIES_ENABLED=false# matikan spot/perp/funding crypto
PAPER_TRADE=true               # AMAN dulu — belum uang asli
```
Harga aset (BTC/ETH/dst) tetap ditarik sebagai input model up/down; yang
dimatikan hanya *trading* crypto-nya. Semua fitur web tetap hidup.

## Dua tahap: PAPER dulu, LIVE nanti

### 🟢 PAPER (default) — 100% gratis, tanpa risiko
- Bet disimulasikan; PnL dihitung dari resolusi market nyata.
- **Tidak ada uang asli, tidak perlu private key.** Ideal untuk validasi.
- Jalan penuh di stack gratis (Oracle + domain). Web menampilkan flow & PnL
  persis seperti live, tapi angkanya paper.
- **WAJIB**: buktikan *positive expectancy* ≥30 hari sebelum live (README).

### 🔴 LIVE — web tetap gratis, TAPI modal = uang asli
Untuk benar-benar eksekusi order di Polymarket:
1. Dompet Polygon terpisah (khusus bot), isi **USDC** + sedikit **POL** (gas).
2. Set di `.env` (JANGAN pernah commit / kirim ke siapa pun):
   ```
   PAPER_TRADE=false
   POLYMARKET_PRIVATE_KEY=<private key dompet bot>
   POLYMARKET_SANDBOX=false
   ```
3. Jalankan `scripts/verify_approvals.py` (allowance USDC ke CLOB) lalu
   `scripts/manual_live_test.py` untuk 1 order uji kecil sebelum otomatis.
4. Mulai dari nominal super kecil. Naikkan hanya setelah paper + live-kecil oke.

> ⚠️ **Keamanan:** private key = akses penuh ke dana dompet itu. Simpan hanya di
> `.env` server (permission 600), pakai dompet khusus bot berisi sedikit dana,
> dan **jangan pernah** mengirimkannya ke chat/PR/orang lain — termasuk saya.

## Hosting gratis (sudah beres)

- Backend + engine + Redis + Postgres → **Oracle Always Free** (`docs/07`).
- Domain `pusatbanksoal.online` + HTTPS → **Cloudflare** (`docs/08`).
- Frontend → di Oracle (Pola 1) atau **Vercel** (Pola 2).

Perintah:
```bash
# Pola 1 — semua di Oracle, domain sendiri
sudo DOMAIN=pusatbanksoal.online bash deploy/oracle-setup.sh
```

## Realistis (jujur)

Screenshot "profit $1 juta / Sharpe 4.82 / APY 36,540%" yang beredar itu
**materi marketing**, bukan hasil terverifikasi. Market Polymarket jangka pendek
efisien; pure up/down ≈ 50/50 dikurangi fee = *house edge*. Web ini memaksimalkan
peluang lewat kecepatan + multi-sinyal + disiplin risiko — **bukan jaminan
profit**. Pakai paper dulu, ukur jujur, baru pertimbangkan live dengan uang yang
Anda siap kehilangan.
