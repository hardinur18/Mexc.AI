# MEXC Futures Notes

Rujukan implementasi awal:

- Base URL: `https://api.mexc.com`
- Public ping: `GET /api/v1/contract/ping`
- Contract info: `GET /api/v1/contract/detail/country`
- Asset: `GET /api/v1/private/account/asset/{currency}`
- Open positions: `GET /api/v1/private/position/open_positions`
- Place order: `POST /api/v1/private/order/create`
- Change leverage: `POST /api/v1/private/position/change_leverage`

Private request headers:

- `ApiKey`
- `Request-Time`
- `Signature`
- `Recv-Window`
- `Content-Type: application/json`

Signature target:

```text
accessKey + timestampMillis + parameterString
```

For GET/DELETE, `parameterString` is query params sorted by key and joined with `&`.
For POST, `parameterString` is the JSON body string.

