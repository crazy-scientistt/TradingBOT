# Railway topology

Three services in one Railway project. GoldGuard is the only public surface.
OpenCodex and Hermes stay on the private network. Do not attach a public domain
to either private service.

## Services

| Service | Public | Private hostname | Port | Build | Volume |
|---------|--------|------------------|------|-------|--------|
| GoldGuard (app) | yes | `goldguard.railway.internal` | `$PORT` | `backend/Dockerfile` via `railway.app.toml` | `/data` |
| OpenCodex | no | `opencodex.railway.internal` | `10100` | `gateway/Dockerfile` | `/app/.opencodex` |
| Hermes | no | `hermes.railway.internal` | `8642` | `hermes/Dockerfile` | `/opt/data` |

App private dependencies:

- OpenCodex: `http://opencodex.railway.internal:10100`
- Hermes: `http://hermes.railway.internal:8642`

## Volumes

- GoldGuard writes SQLite/WAL only to `/data`.
- OpenCodex persists provider state only at `/app/.opencodex`.
- Hermes persists agent data only at `/opt/data`.

## Replica rule

One GoldGuard writer replica owns SQLite/WAL. Scaling beyond one writer requires
a reviewed database architecture change. OpenCodex and Hermes also run as a
single replica each unless their own storage model is redesigned.

## Health

- GoldGuard liveness: `GET /api/health/live` (process loop only).
- GoldGuard readiness: `GET /api/health/ready` (database initialised).
- Trading readiness blockers live on `GET /api/diagnostics`, not on liveness.
