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
4. Di Cloudflare → **DNS** → **Add record**:
   | Type | Name | Content | Proxy |
   |---|---|---|---|
   | A | `@` | `<IP_PUBLIK_ORACLE>` | 🟠 Proxied |
   | A | `www` | `<IP_PUBLIK_ORACLE>` | 🟠 Proxied |
5. Cloudflare → **SSL/TLS** → mode **Flexible** (browser↔CF HTTPS, CF↔VM HTTP:80
   — cocok dengan `nginx.free.conf` apa adanya, tanpa sertifikat di VM).
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

### A. Backend (Oracle) di subdomain
1. Cloudflare DNS: `A  api  <IP_ORACLE>  🟠 Proxied`, SSL/TLS **Flexible**.
2. Deploy VM: `sudo DOMAIN=api.pusatbanksoal.online bash deploy/oracle-setup.sh`
   → backend reachable di `https://api.pusatbanksoal.online`.

### B. Frontend di Vercel
1. Vercel → **Add New Project** → import repo `panjivr/ultra-arb`.
2. **Root Directory:** `arb/dashboard/frontend`  ·  Framework: **Next.js**.
3. **Environment Variables:**
   - `NEXT_PUBLIC_API_URL = https://api.pusatbanksoal.online`
   - `NEXT_PUBLIC_WS_URL  = wss://api.pusatbanksoal.online`
4. Deploy → Vercel → **Domains** → tambah `pusatbanksoal.online`.
   - Vercel kasih target CNAME. Karena root domain (`@`) diproxy Cloudflare,
     pakai **CNAME `@` → cname.vercel-dns.com** (Cloudflare izinkan CNAME flatten
     di root). Set record ini **DNS-only (abu-abu)** sesuai instruksi Vercel.
5. Di backend, pastikan `CORS_ORIGINS` memuat `https://pusatbanksoal.online`
   (script sudah isi kalau `DOMAIN` diset; kalau perlu, edit `.env` lalu
   `docker compose -f docker-compose.free.yml up -d`).

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
