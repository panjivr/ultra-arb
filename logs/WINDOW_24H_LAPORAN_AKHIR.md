# Window 24h Selesai — Laporan Akhir
Generated: 2026-05-18 (Claude Code)
Window: 2026-05-16T22:46:26Z → 2026-05-17T22:46:26Z (24.22h actual)

---

## Verdict Resmi: ⚪ INSUFFICIENT_DATA

**Next action: DO_NOT_LIVE. Modal Rp 200.000 → SAVED.**

---

## Data Mentah (T+24h snapshot)

| Metric | Value |
|--------|-------|
| Window duration | 24.22 jam actual |
| arb:orders count | 1088 total (544 CLOSE events) |
| arb:polymarket:bets | **0** |
| arb:poly:resolved | **0** |
| Crypto PnL | **-$26.78** (544 trades, win rate 32%) |
| Polymarket PnL | **$0.00** (0 bets) |
| arb:poly:stats keys | (kosong — tidak ada bet) |
| Container restarts (Docker policy) | 0 |
| rule5 manual restarts | **23 kali** |
| Redis memory | 123.98MB |
| Error count (last 6h) | 10 (reyog_edges) |
| Risk halted | 0 kali |

### Breakdown Crypto (544 trades)
- Strategy: CrossExchange only
- PnL: -$26.78 total, -$0.0492 avg/trade
- Win rate: 32% (174W / 370L)
- EV per trade: **negatif** — edge tidak ada

---

## Status Opsi A (Bypass Ensemble)

**NOT_APPLIED.** Tidak ada commit G2.1. Kode masih original:
```python
# scripts/real_market_engine.py line 599-606
try:
    from arb.edges.ensemble import evaluate, SignalVote, emit_vote
    _ensemble_enabled = True  # ← ENABLED, 3-of-4 gate aktif
    print("[poly] ensemble gate: ENABLED ...")
except ImportError:
    _ensemble_enabled = False  # hanya jika import gagal
```

Penyebab 0 bets sudah dikonfirmasi (investigasi sebelumnya):
- `arb:edges:votes` stream: 5003 entries, **semua dari `source="momentum"` (Cluster A)**
- `arb:edges:approved` key: **none** — tidak pernah ada yang lolos gate
- Gate butuh 3 cluster independen; hanya 1 cluster (A) yang pernah vote
- Edge detectors (yesno_arb, smart_money, dll) publish ke `arb:edges:*` tapi TIDAK ke `arb:edges:votes` → tidak pernah memanggil `emit_vote()`

---

## Status Rule5 Restart Loop

**Noisy — tidak merusak data, tapi membuat window 24h tidak "clean".**

| Metric | Value |
|--------|-------|
| rule5 triggers | 23 kali |
| Engine restarts total | 25 kali |
| Penyebab | CRYPTO_STRATEGIES_ENABLED=false → arb:signals berhenti naik → rule5 mengira engine macet |
| Damage assessment | **NONE** — Redis persists. arb:orders/bets tidak terpengaruh restart |
| Engine state sekarang | **Running=false** (docker stop at T+24h ✅) |

Container restarts menurut Docker restart policy = 0 (rule5 pakai `docker restart` manual, bukan restart policy → tidak ter-track di `RestartCount`). Ini adalah gap monitoring.

---

## Insight Penting

1. **Ensemble gate adalah single point of failure** — dirancang untuk 4 cluster tapi hanya 1 yang wired. Desain ini mustahil dilewati tanpa wire semua edge detector ke `emit_vote()`.

2. **Crypto edge terbukti negatif 2x** — Demo 1h (-$1.15), Window 24h (-$26.78). Win rate 32% secara konsisten. CrossExchange spread HTX↔Gate.io < 4bps roundtrip cost. Bukan edge.

3. **rule5 perlu direvisi** — Signal stall detection harus pakai `arb:ticks:*` count (ticks selalu naik selama engine hidup), BUKAN `arb:signals` (yang memang berhenti setelah G2 kill-switch).

4. **Polymarket market fetching masih bisa lebih baik** — `tag_id=21` mengembalikan pasar FDV/long-term yang difilter oleh `hours_left > 240`. Perlu verifikasi apakah BTC Up/Down markets ada di tag lain.

5. **Engine berhasil di-stop at T+24h** — Dataset freeze bekerja. DONE sentinel ditulis 2026-05-17T23:00Z, post_window_decision.py auto-run di 23:30Z. Autonomous monitoring pipeline bekerja end-to-end.

---

## Rekomendasi Claude Code

### Opsi A — Bypass Ensemble (cepat, data dalam 24h)
Ubah 1 baris di `real_market_engine.py`:
```python
# Ganti:
_ensemble_enabled = True
# Jadi:
_ensemble_enabled = False  # G2.1: bypass — wire detectors ke emit_vote() di G3
```
**Pro:** Bets akan flow langsung berdasarkan momentum + edge threshold.
**Con:** Tanpa ensemble, lebih banyak false signal. Kualitas data lebih rendah tapi ada data.
**Fix tambahan required:** rule5 harus pakai `arb:ticks:*` bukan `arb:signals`.

### Opsi B — Wire Edge Detectors ke emit_vote() (benar tapi lama)
Setiap edge (yesno_arb, smart_money, time_decay, related_markets, news_reaction) memanggil `emit_vote()` untuk setiap condition_id yang mereka deteksi. Ensemble berjalan seperti dirancang.
**Pro:** Data berkualitas tinggi, ensemble filtering valid.
**Con:** 5+ file edge harus dimodifikasi dan dikoordinasikan. Perlu 1-2 jam coding + testing.

### Opsi C — Window ulang tanpa fix (tidak direkomendasikan)
Hasil akan sama: 0 bets. Tidak ada data baru yang bisa dipelajari.

**Rekomendasi: Opsi A + fix rule5, kemudian window 24h baru.**

---

## Modal Rp 200.000

**Status: SAVED — tidak deployed.**

Rekomendasi: **HOLD sampai window kedua (post-Opsi A) menghasilkan data Polymarket.**
- Jika window kedua: Polymarket PnL > 0 AND win_rate ≥ 55% AND bets ≥ 30 → pertimbangkan G4
- Jika window kedua: hasil negatif/insufficient → apply F4/F5 modeling fix dulu

---

## Pertanyaan Untuk User

1. **Opsi A atau B?** — Bypass ensemble cepat (Opsi A, ~30 menit deploy) vs wire edge detectors benar (Opsi B, ~2 jam). Atau tunggu lebih lama?

2. **Rule5 fix** — Ganti `arb:signals` check dengan `arb:ticks:*` count di `window_24h_monitor.py`? Ini memastikan rule5 tidak fire false-positive saat crypto disabled. **Perlu approval sebelum apply.**

3. **Window 24h baru** — Setelah Opsi A + rule5 fix di-deploy, start window baru langsung? Atau ada hal lain yang mau dicek dulu?

---

## Files Updated Session Ini

```
logs/window_24h_FINAL.md          ← pulled dari VPS
logs/post_window_decision.md      ← pulled dari VPS
logs/window_24h_T+24h.json        ← pulled dari VPS
logs/WINDOW_24H_LAPORAN_AKHIR.md  ← file ini (baru)
```

## Commits Session Ini

```
5cb23cf  G2: add post_window_decision.py — auto-verdict at T+24h sentinel
a775c09  G2: crypto kill-switch deployed — emit_signals+emit_trades stopped
231aec7  G4-prep: demo 1h PASS — all 6 criteria green, G4 artifacts generated
46a4bae  G4-prep: add demo_paper_1h.py — 1h paper observation + auto-verdict
bf13cfd  G1.3: add 24h honest-window autonomous monitor
24db3ef  docs: record G1.1-poly/G1.1-prod state + divergence notes
```

---

_Laporan ini dibuat berdasarkan data real VPS. Semua angka verified dari Redis + docker logs._
