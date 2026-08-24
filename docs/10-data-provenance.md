# 10 — Peta Data: mana ASLI, mana PAPER, mana DUMMY

> Ditulis setelah audit "hilangkan semua dummy". Ringkas: **dashboard sudah
> disuapi data ASLI**. Yang disimulasikan hanya **uang** (mode paper) — dan itu
> pilihan keamanan, bukan dummy. Tidak ada lagi angka yang dikarang.

## Definisi (penting, sering tertukar)
- **ASLI (REAL):** ditarik langsung dari API pasar/publik, live.
- **PAPER:** memakai data pasar ASLI, tapi eksekusi/PnL dihitung dengan **modal
  simulasi** (tidak menaruh uang beneran). Bukan dummy — hasil bergantung pada
  pergerakan & resolusi pasar nyata.
- **DUMMY:** angka dikarang (random/hardcoded) yang tidak mewakili apa pun.
  **Target: nol.**

## Tabel provenance

| Panel / data | Sumber | Status |
|---|---|---|
| Harga crypto (BTC/ETH/SOL/BNB/XRP) | Gate.io + HTX public API | 🟢 ASLI |
| Spread cross-exchange | dihitung dari 2 harga ASLI | 🟢 ASLI |
| Market Polymarket (harga YES/NO, likuiditas) | `gamma-api.polymarket.com` | 🟢 ASLI |
| Whale trades / smart-money | `data-api.polymarket.com/trades` | 🟢 ASLI |
| 6 edge detector (yesno, smart_money, time_decay, related, news, basis) | API Polymarket + RSS | 🟢 ASLI |
| Funding rate | Gate.io + HTX futures API | 🟢 ASLI *(baru — dulu dikarang)* |
| Macro (DXY/Gold/VIX/Fear&Greed/dominance) | API publik gratis | 🟢 ASLI |
| Berita | RSS Cointelegraph/Decrypt/TheBlock | 🟢 ASLI |
| Kalender ekonomi (FOMC/CPI/NFP 2026) | jadwal publik resmi (hardcoded, memang tetap) | 🟢 ASLI |
| Latency (ns tick→decision) | sampel waktu nyata di Redis | 🟢 ASLI |
| Saldo wallet | Polygon RPC saat wallet di-connect | 🟢 ASLI *(butuh connect wallet)* |
| **Eksekusi bet + PnL Polymarket** | sinyal ASLI, resolusi pasar ASLI, **modal simulasi** | 🟡 PAPER |
| Fake funding `random.gauss` | — | ❌ **DIHAPUS** |

## Yang diubah pada audit ini
1. **`scripts/real_market_engine.py` → `emit_funding()`**: dulu
   `random.gauss(...)` (funding palsu). Sekarang **fetch funding asli** dari
   Gate.io (`/futures/usdt/contracts/…`) + HTX (`/linear-swap-api/…`). Gagal
   fetch → dilewati, tidak dipalsukan.
2. Dikonfirmasi: semua edge detector & feed harga sudah pakai API asli; tidak
   ada generator angka palsu lain yang menyuapi dashboard.
3. `random` yang tersisa di engine hanya **jitter waktu** (jeda antar-loop),
   bukan nilai data.

## Satu-satunya cara membuat eksekusi jadi "uang beneran"
Mode PAPER → LIVE **bukan** soal menghapus dummy (sudah tidak ada). Itu soal
**menaruh modal nyata**:
1. Dompet Polygon berisi **USDC** + sedikit **POL** (gas).
2. `.env` di server: `PAPER_TRADE=false`, `POLYMARKET_PRIVATE_KEY=<kunci>`,
   `POLYMARKET_SANDBOX=false`.
3. Uji kecil (`scripts/verify_approvals.py`, `scripts/manual_live_test.py`)
   sebelum otomatis penuh.

⚠️ Private key = akses penuh dana dompet. Isi hanya di server, dompet khusus
bot, jangan pernah dikirim ke chat/PR/siapa pun. Dan ingat: market prediksi
jangka pendek efisien — live = risiko rugi nyata. Paper-kan dulu, ukur jujur.
