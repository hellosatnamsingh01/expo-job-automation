# Railway Deployment Guide

## Step 1 — Push to GitHub
Make sure your code is pushed to a GitHub repository.

## Step 2 — Create Railway Project
1. Go to railway.app → New Project → Deploy from GitHub repo
2. Select your repository

## Step 3 — Add Plugins (Databases)
In your Railway project, click **+ New** and add:
- **PostgreSQL** plugin
- **Redis** plugin

Railway will auto-generate connection URLs for both.

## Step 4 — Create 4 Services
Click **+ New → GitHub Repo** (same repo) for each:

| Service Name | Root Directory | Start Command Override |
|---|---|---|
| `backend` | `/backend` | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| `celery-worker` | `/backend` | `celery -A app.tasks.celery_app worker --pool=solo --loglevel=info --queues=celery,send` |
| `celery-beat` | `/backend` | `celery -A app.tasks.celery_app beat --loglevel=info` |
| `frontend` | `/frontend` | `node server.js` |

## Step 5 — Set Environment Variables

### backend, celery-worker, celery-beat (all 3 share same vars)
```
DATABASE_URL=postgresql+asyncpg://<from Railway PostgreSQL plugin>
SYNC_DATABASE_URL=postgresql://<from Railway PostgreSQL plugin>
REDIS_URL=<from Railway Redis plugin>

SECRET_KEY=<generate a random 32-char string>
ALGORITHM=HS256

ANTHROPIC_API_KEY=<your key>
OPENAI_API_KEY=<your key>

GMAIL_CLIENT_ID=<your Gmail OAuth client ID>
GMAIL_CLIENT_SECRET=<your Gmail OAuth client secret>
GMAIL_REDIRECT_URI=https://<your backend Railway domain>/api/v1/auth/gmail/callback

APP_URL=https://<your backend Railway domain>
FRONTEND_URL=https://<your frontend Railway domain>
TRACKING_PIXEL_URL=https://<your backend Railway domain>/api/v1/track

HUNTER_API_KEYS=<your Hunter.io keys>
HASDATA_API_KEY=<your HasData key>

STORAGE_PATH=/storage
```

### frontend only
```
NEXT_PUBLIC_API_URL=https://<your backend Railway domain>/api/v1
```

## Step 6 — Persistent Storage (important!)
The backend stores CV files and generated PDFs in `/storage`.
In Railway, go to your **backend** service → **Volumes** → Add volume:
- Mount path: `/storage`
- Size: 1GB

Do the same for **celery-worker** (mount same volume so worker can read CVs).

## Step 7 — Run Database Migrations
After backend deploys, open Railway shell for the backend service and run:
```bash
alembic upgrade head
```

## Step 8 — Update Gmail OAuth
In Google Cloud Console → OAuth credentials → add your Railway backend URL to:
- Authorised redirect URIs: `https://<backend-domain>/api/v1/auth/gmail/callback`

## Notes
- Railway auto-assigns domains like `backend-production-xxxx.up.railway.app`
- PostgreSQL and Redis URLs are auto-injected when you use Railway plugins
- celery-worker and celery-beat use the same Docker image as backend, just different start commands
