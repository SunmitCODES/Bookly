# Bookly — Deployment Guide (Railway + Supabase + Sentry)

## 1. Database: switch to Supabase Postgres (step 28)

The code is already database-agnostic — `app/database.py` reads `DATABASE_URL` from
the environment and the custom `GUID` type (`app/db_types.py`) works on both SQLite
and Postgres. **Switching to Supabase is just an env var change — no code edits.**

1. In Supabase → Project Settings → Database → Connection string (URI), copy the
   connection string. Use the **connection pooler** URI for serverless/Railway.
2. SQLAlchemy needs the `postgresql://` scheme (Supabase sometimes shows
   `postgres://` — change `postgres://` to `postgresql://`).
3. Set it as `DATABASE_URL` in Railway (see below).

Tables auto-create on startup via `Base.metadata.create_all` in `app/main.py`.
> Hardening (later): replace `create_all` with Alembic migrations (already a dependency)
> once the schema stabilises, so production schema changes are versioned.

## 2. Deploy to Railway (step 27)

The repo includes a `Dockerfile`, `.dockerignore`, and `railway.json`
(Dockerfile build + `/health` health check).

1. Push the project to GitHub.
2. Railway → New Project → Deploy from GitHub repo → pick this repo.
3. Railway detects the Dockerfile automatically.
4. Add the environment variables below (Railway → Variables).
5. Deploy. Railway sets `$PORT`; the Dockerfile's `CMD` binds to it.
6. Your app is at `https://<project>.up.railway.app`.

### Required environment variables on Railway
```
DATABASE_URL=postgresql://...           # Supabase pooler URI
SECRET_KEY=<long random string>
ENVIRONMENT=production                   # makes auth cookies Secure
SUPABASE_URL=...                         # (kept for future supabase-py use)
SUPABASE_KEY=...
RAZORPAY_KEY_ID=rzp_live_or_test_...
RAZORPAY_KEY_SECRET=...
RAZORPAY_WEBHOOK_SECRET=whsec_...
RAZORPAY_PLAN_PRO=plan_...
RAZORPAY_PLAN_BUSINESS=plan_...
RESEND_API_KEY=re_...
EMAIL_FROM=bookings@yourverifieddomain.com
GUPSHUP_API_KEY=...                      # for WhatsApp (step 17)
REDIS_URL=redis://...                    # add a Railway Redis plugin for reminders (step 16)
SENTRY_DSN=https://...@sentry.io/...     # optional; blank = disabled
```

## 3. Sentry error monitoring (step 26)

`app/main.py` initialises Sentry only when `SENTRY_DSN` is set (blank in dev =
disabled, zero overhead). To enable:
1. Create a project at sentry.io → copy the DSN.
2. Set `SENTRY_DSN` on Railway.
Errors and 10% of traces are then reported automatically.

## 4. Razorpay webhook (needs the live URL)

Once deployed, in the Razorpay dashboard add a webhook:
`https://<project>.up.railway.app/payments/webhook/razorpay`
subscribed to `subscription.*` events, with the same secret as `RAZORPAY_WEBHOOK_SECRET`.

## 5. Reminders worker (steps 16–17)

Reminders run in a Celery worker + Beat scheduler, separate from the web app,
sharing the same `REDIS_URL`.

**Local (Windows):**
```powershell
celery -A app.tasks.celery_app worker --beat -l info --pool=solo
```
(`--pool=solo` is required on Windows. On Linux/Mac, drop it.)

**Railway:** add a **Redis** plugin (gives `REDIS_URL`), then add a **second service**
from the same repo with the start command:
```
celery -A app.tasks.celery_app worker --beat -l info
```
Give it the same env vars as the web service (esp. `DATABASE_URL`, `REDIS_URL`,
`RESEND_API_KEY`, `GUPSHUP_*`).

**WhatsApp (Gupshup) — to go live:** register a WhatsApp sender, set
`GUPSHUP_API_KEY`, `GUPSHUP_SOURCE` (sender number), `GUPSHUP_APP_NAME`, and create
an **approved message template** (business-initiated WhatsApp requires templates).
Until then, reminders send by email only — WhatsApp is a safe no-op.

## 6. Logo uploads — Cloudflare R2 (step 25)

1. Cloudflare → R2 → create a bucket (e.g. `bookly-logos`).
2. Enable public access: either turn on the bucket's **r2.dev public URL**, or
   attach a **custom domain**. Copy that base URL.
3. R2 → Manage API Tokens → create a token with Object Read & Write; copy the
   Access Key ID + Secret.
4. Set these env vars (also work locally in `.env`):
```
R2_ACCOUNT_ID=<your cloudflare account id>
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET=bookly-logos
R2_PUBLIC_BASE_URL=https://pub-xxxx.r2.dev   # or your custom domain
```
Until these are set, the dashboard shows "connect image storage to enable uploads"
and the upload endpoints return 503 — the rest of the app is unaffected.

## 7. Post-deploy smoke test
- `GET /health` → `{"status": "ok"}`
- `GET /docs` loads
- Sign up at `/signup`, create a business, open `/b/<slug>`, make a booking.
