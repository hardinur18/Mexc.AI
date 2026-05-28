# Setup Lokal MEXC Future Dashboard

## Prasyarat

- **Python 3.9+** â€” https://www.python.org/downloads/
  - Saat install, centang **"Add Python to PATH"**
- **Node.js 18+** â€” https://nodejs.org/ (sudah terinstall)

---

## Langkah 1 â€” Install Python Dependencies

Buka terminal di folder project, lalu jalankan:

```bash
cd "d:/Project Web/Mexc Future/MEXC-Future"
python -m pip install -e .
pip install fastapi uvicorn pydantic websockets
```

## Langkah 2 â€” Buat File .env

Copy dari template:

```bash
cp .env.example .env
```

Isi `.env` dengan API key MEXC kamu:

```
MEXC_ACCESS_KEY=isi_access_key_kamu
MEXC_SECRET_KEY=isi_secret_key_kamu
MEXC_BASE_URL=https://api.mexc.com
MEXC_LIVE_TRADING_ENABLED=false
```

> API Key bisa dibuat di: **MEXC â†’ Account â†’ API Management â†’ Create API Key**

## Langkah 3 â€” Jalankan Backend

```bash
cd "d:/Project Web/Mexc Future/MEXC-Future/ui"
python server.py
```

Backend akan jalan di `http://localhost:8787`

## Langkah 4 â€” Jalankan Frontend

Buka terminal baru:

```bash
cd "d:/Project Web/Mexc Future/MEXC-Future/ui-web"
npm install
npm run dev
```

Frontend akan jalan di `http://localhost:5173`

## Langkah 5 â€” Buka di Browser

Buka **http://localhost:5173**

---

## Tambah Akun Baru

API key disimpan di file **`accounts.json`** (lokal, tidak ke-push ke Git).

Buka `accounts.json` di root project, tambahkan akun baru di dalam array `accounts`:

```json
{
  "accounts": [
    {
      "id": "scalp_bot",
      "name": "Scalp Bot",
      "color": "#22c55e",
      "category": "utama",
      "access_key": "isi_access_key",
      "secret_key": "isi_secret_key"
    },
    {
      "id": "isi_id_unik",
      "name": "isi_nama_tampilan",
      "color": "#pilih_warna",
      "category": "isi_kategori",
      "access_key": "isi_access_key",
      "secret_key": "isi_secret_key"
    }
  ]
}
```

### Template siap paste untuk akun kedua

Kalau `accounts.json` kamu saat ini sudah punya akun pertama, format akhirnya kurang lebih seperti ini. Ganti hanya bagian `ISI_ACCESS_KEY_AKUN_2` dan `ISI_SECRET_KEY_AKUN_2`:

```json
{
  "accounts": [
    {
      "id": "mexc_one",
      "name": "mexc one",
      "color": "#22c55e",
      "category": "utama",
      "access_key": "ACCESS_KEY_AKUN_1_YANG_SUDAH_ADA",
      "secret_key": "SECRET_KEY_AKUN_1_YANG_SUDAH_ADA"
    },
    {
      "id": "mexc_two",
      "name": "mexc two",
      "color": "#3b82f6",
      "category": "utama",
      "access_key": "ISI_ACCESS_KEY",
      "secret_key": "ISI_SECRET_KEY"
    }
  ]
}
```

Kalau mau paste hanya object akun kedua, tambahkan koma setelah akun pertama lalu paste blok ini:

```json
{
  "id": "mexc_two",
  "name": "mexc two",
  "color": "#3b82f6",
  "category": "utama",
  "access_key": "ISI_ACCESS_KEY",
   "secret_key": "ISI_SECRET_KEY"
}
```

Checklist MEXC API untuk akun kedua:

- Permission minimal: baca akun/posisi/order. Jangan aktifkan withdraw.
- Kalau pakai IP whitelist, masukkan IP publik mesin/server yang menjalankan backend.
- Pastikan akun kedua adalah Futures-enabled.
- Setelah simpan `accounts.json`, restart backend:

```bash
cd "d:/Project Web/Mexc Future/MEXC-Future/ui"
python server.py
```

Tes akun dari UI:

1. Buka `http://localhost:5173`
2. Masuk halaman **Akun**
3. Pastikan `mexc two` muncul
4. Kalau gagal konek, cek pesan error di terminal backend

### Yang harus diisi per akun:

| Field | Keterangan | Contoh |
|-------|-----------|--------|
| `id` | ID unik internal (huruf kecil, angka, underscore) | `bot_2` |
| `name` | Nama tampilan di dashboard | `Akun Kedua` |
| `color` | Warna badge (hex) | `#3b82f6` |
| `category` | Grup akun | `utama`, `radar`, `booster` |
| `access_key` | API Access Key dari MEXC | `mx0vgl...` |
| `secret_key` | API Secret Key dari MEXC | `abc123...` |

### Pilihan warna:

- Hijau: `#22c55e`
- Biru: `#3b82f6`
- Cyan: `#06b6d4`
- Kuning: `#eab308`
- Merah: `#ef4444`
- Ungu: `#a855f7`
- Lime: `#84cc16`

> Setelah edit `accounts.json`, **restart backend** (`python server.py`) supaya akun baru terbaca.

---

## Catatan Penting

- Backend (port 8787) **harus jalan duluan** sebelum buka frontend
- API key disimpan **lokal saja** di file `accounts.json` (tidak dikirim ke server luar)
- `MEXC_LIVE_TRADING_ENABLED=false` â€” trading live mati secara default, aman untuk testing
- Jika DNS diblokir ISP, tambahkan di `.env`:
  ```
  MEXC_USE_DOH_DNS=true
  MEXC_DOH_URL=https://cloudflare-dns.com/dns-query
  ```
