# Network Policy

Tujuan: akses MEXC API real dari local tanpa mock dan tanpa mengorbankan API key.

## Keputusan

Gunakan DNS-over-HTTPS Cloudflare sebagai default local workaround:

```text
MEXC_USE_DOH_DNS=true
MEXC_DOH_URL=https://cloudflare-dns.com/dns-query
```

Alasannya:

- Gratis.
- Cepat.
- Tidak melewatkan request API key melalui random VPN provider.
- Masalah lokal yang terjadi adalah DNS poisoned ke `internetpositif.ioh.co.id`, bukan MEXC API down.
- TLS tetap diverifikasi ke host asli `api.mexc.com`.

## Jangan Pakai

Hindari random free VPN untuk private endpoint trading:

- provider bisa lambat atau tidak stabil
- bisa punya DNS/proxy aneh
- bisa memicu exchange risk checks
- tidak ideal untuk secret API trading

## Boleh Pakai

Kalau DoH tidak cukup:

- VPN pribadi yang tepercaya
- WARP/Cloudflare
- Tailscale exit node milik sendiri
- VPS kecil tepercaya untuk runtime live

Untuk saat ini local development memakai DoH override dan sudah terbukti:

- `ping` MEXC sukses
- REST public sukses
- REST private read-only sukses
- WebSocket public sukses
- WebSocket private login sukses

