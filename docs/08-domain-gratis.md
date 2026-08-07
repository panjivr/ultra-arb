# 08 — Pasang domain `pusatbanksoal.online` GRATIS (HTTPS, tanpa hosting bayar)

> Anda sudah punya domain aktif di DomaiNesia. Dokumen ini menyambungkannya ke
> REYOG **gratis selamanya + HTTPS**, lewat **Cloudflare** (paket Free). Tidak
> ada biaya hosting.

## Kenyataan penting dulu (jujur)

REYOG **bukan situs statis**. Ada bagian yang WAJIB always-on dan **tidak bisa
di Vercel**: engine tick 24/7, 6 edge scanner, WebSocket firehose, Redis,
Postgres. Vercel hanya cocok untuk **frontend**. Jadi "otak"-nya tetap di
**Oracle Always Free VM** (gratis selamanya). Domain tinggal diarahkan.

Ada 2 pola. Keduanya **Rp0** dan pakai `pusatbanksoal.online`.

## Pembagian tugas (apa yang otomatis vs yang cuma Anda bisa klik)

**Sudah diotomatiskan (script di repo, tinggal jalan):**
- Buat semua DNS record + set SSL Flexible → `deploy/cloudflare-dns.sh`
- Setup server + backend + CORS + URL domain → `deploy/oracle-setup.sh`
- Konfigurasi frontend (env, WS langsung) → sudah beres di kode

**Hanya bisa Anda lakukan (butuh login akun Anda — saya tak punya aksesnya):**
- Provision VM Oracle (butuh verifikasi kartu Anda) → dapat **IP publik**
- Tambah `pusatbanksoal.online` ke Cloudflare & buat **API token**
- Ganti **Nameserver** di DomaiNesia ke NS Cloudflare
- (Pola 2) Klik **Add Domain** di Vercel untuk record CNAME root

Kirimkan **IP Oracle** + **CF API token** ke sesi ini kalau mau saya jalankan
langsung `cloudflare-dns.sh` dari sini untuk Anda.

---

## Pola 1 — Semua di Oracle, domain via Cloudflare  *(REKOMENDASI, paling simpel)*

Frontend **dan** backend jalan di VM Oracle. Cloudflare kasih HTTPS gratis.

```
Browser ──HTTPS──> Cloudflare (TLS gratis) ──HTTP:80──> Oracle VM (nginx.free.conf)
                                                          └─ semua service REYOG
```

### Langkah

1. **Buat akun Cloudflare (gratis)** → **Add a site** → ketik
   `pusatbanksoal.online`.
2. Cloudflare kasih **2 nameserver** (mis. `xxx.ns.cloudflare.com`).
3. Di **DomaiNesia**: menu domain → **Nameservers** → ganti ke 2 NS Cloudflare
   itu → Save. (Propagasi 5 menit–beberapa jam.)
4. **DNS + SSL otomatis** (buat A `@`/`www` → IP Oracle + set Flexible):
   ```bash
   CF_API_TOKEN=<token> ZONE=pusatbanksoal.online IP=<IP_PUBLIK_ORACLE> \
     bash deploy/cloudflare-dns.sh pola1
   ```
   Token dibuat sekali di Cloudflare → My Profile → API Tokens → template
   **"Edit zone DNS"** untuk zona `pusatbanksoal.online`.
   *(Manual alternatif: DNS → Add record A `@` & `www` → IP, Proxied; lalu
   SSL/TLS → Flexible.)*
6. Deploy di VM **dengan domain**:
   ```bash
   cd ultra-arb
   sudo DOMAIN=pusatbanksoal.online bash deploy/oracle-setup.sh
   ```
   (Script mengeset `NEXT_PUBLIC_API_URL=https://pusatbanksoal.online`,
   `NEXT_PUBLIC_WS_URL=wss://...`, dan CORS ke domain.)

Buka **`https://pusatbanksoal.online`** 🎉 — gembok hijau, gratis.

> **Upgrade keamanan (opsional):** ganti SSL/TLS ke **Full** lalu pasang
> **Cloudflare Origin Certificate** di VM (nginx :443). Untuk paper-trading,
> Flexible sudah cukup.

---

## Pola 2 — Frontend di Vercel, backend di Oracle

Kalau memang mau UI di Vercel (CDN global, deploy dari Git):

```
Browser ─HTTPS─> Vercel (pusatbanksoal.online)      → frontend Next.js
Browser ─WSS/HTTPS─> Cloudflare → Oracle VM         → api.pusatbanksoal.online (backend+WS)
```

### A. Backend (Oracle) di subdomain `api.` — OTOMATIS
1. **DNS otomatis** (buat A record `api` → IP Oracle + set SSL Flexible):
   ```bash
   CF_API_TOKEN=<token> ZONE=pusatbanksoal.online IP=<IP_ORACLE> \
     bash deploy/cloudflare-dns.sh pola2
   ```
2. **Deploy backend dengan CORS ke frontend Vercel** (sekali perintah):
   ```bash
   sudo DOMAIN=api.pusatbanksoal.online FRONT=pusatbanksoal.online \
     bash deploy/oracle-setup.sh
   ```
   → backend live di `https://api.pusatbanksoal.online`, CORS sudah mengizinkan
   `https://pusatbanksoal.online`. **Tak perlu edit `.env` manual.**

### B. Frontend di Vercel
Env sudah disiapkan di `arb/dashboard/frontend/.env.production.example`.
1. Vercel → **Add New Project** → import repo `panjivr/ultra-arb`.
2. **Root Directory:** `arb/dashboard/frontend`  ·  Framework: **Next.js** (auto).
3. **Environment Variables** (Production) — salin dari `.env.production.example`:
   - `NEXT_PUBLIC_API_URL = https://api.pusatbanksoal.online`
   - `NEXT_PUBLIC_WS_URL  = wss://api.pusatbanksoal.online`
4. Deploy → Vercel → **Domains** → tambah `pusatbanksoal.online`. Ikuti record
   CNAME yang Vercel tunjukkan (`@ → cname.vercel-dns.com`, set **DNS-only /
   abu-abu** di Cloudflare). Ini satu-satunya record yang ditambah lewat alur
   Vercel, bukan script.

> WebSocket: `src/lib/api.ts` connect **langsung** ke `NEXT_PUBLIC_WS_URL`
> (bukan lewat rewrite Next), jadi WSS ke backend Oracle via Cloudflare jalan
> di Vercel. Tak ada perubahan kode yang diperlukan.

> Catatan: WebSocket **WSS** lewat Cloudflare Free **didukung**. Frontend Vercel
> (HTTPS) memanggil backend HTTPS/WSS → tidak ada mixed-content.

---

## Mana yang dipilih?

- **Cepat & satu tempat → Pola 1.** Semua di Oracle, domain langsung nyala HTTPS.
  Tidak perlu Vercel sama sekali.
- **Suka workflow Vercel (auto-deploy dari Git, CDN) → Pola 2.** Sedikit lebih
  banyak langkah DNS, tapi UI jadi super cepat global.

Keduanya: **Rp0/bulan, domain sendiri, HTTPS, 24/7.**

---

## Checklist ringkas (Pola 1)

- [ ] Akun Cloudflare, add `pusatbanksoal.online`
- [ ] DomaiNesia → Nameservers → NS Cloudflare
- [ ] Cloudflare DNS: A `@` + `www` → IP Oracle (Proxied)
- [ ] SSL/TLS = Flexible
- [ ] `sudo DOMAIN=pusatbanksoal.online bash deploy/oracle-setup.sh`
- [ ] Buka `https://pusatbanksoal.online`
