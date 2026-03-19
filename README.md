# Gmail Cleanup AI

AI-powered Gmail cleanup assistant with a FastAPI backend, PostgreSQL + pgvector, Redis, Google OAuth Gmail sync, real embeddings, safe Gmail actions, and a React review UI.

## Architecture

- `backend/app/api`: FastAPI routes for auth, email sync, detail views, similarity, and cleanup actions.
- `backend/app/services`: Gmail OAuth/API client, embedding providers, similarity search, hybrid recommendation logic, and policy guardrails.
- `backend/app/models`: SQLAlchemy models for users, Gmail accounts, emails, embeddings, classifications, and user actions.
- `backend/alembic`: migration support for local and containerized environments.
- `frontend`: React + Vite SPA for sign-in, sync, review, and action execution.

## What Works

- Google OAuth login flow for Gmail.
- Encrypted token storage and refresh handling for connected Gmail accounts.
- Real Gmail sync into Postgres without duplicate message creation.
- Swappable embedding provider abstraction with OpenAI-compatible embeddings and optional fake provider for tests.
- pgvector similarity search over stored email embeddings.
- Hybrid recommendations combining rules, similar-email history, and optional LLM fallback.
- Safe Gmail actions: archive, trash, apply labels, and mark as read.
- Review-first UI with recommendation display, similar emails, and action history.

## Safety Model

- High-risk email patterns are protected first: OTP/security, banking, travel, interview, invoice/receipt, and important sender/domain patterns.
- Archive and trash are blocked for high-risk email unless `confirm_high_risk=true` is explicitly sent by the client.
- No permanent delete endpoint is exposed.

## Environment Variables

Backend variables live in `backend/.env.example`.

Required values:

- `SECRET_KEY`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `EMBEDDING_API_KEY` when `EMBEDDING_PROVIDER=openai`

Optional LLM values:

- `LLM_PROVIDER=openai`
- `LLM_MODEL`
- `LLM_API_KEY`

Frontend variables live in `frontend/.env.example`.

## Local Run

1. Copy `backend/.env.example` to `backend/.env`.
2. Copy `frontend/.env.example` to `frontend/.env`.
3. Set your Google OAuth redirect URI to `http://localhost:8000/auth/google/callback`.
4. From the repo root, run `docker compose up --build`.

Endpoints:

- Frontend: `http://localhost:5173`
- API: `http://localhost:8000`
- Health check: `http://localhost:8000/health`

## Database Migrations

Run from `backend/`:

```bash
alembic upgrade head
```

The app still includes startup schema compatibility upgrades so the prototype database can be brought forward without a destructive reset.

## API Examples

Get the Google login URL:

```bash
curl http://localhost:8000/auth/google/login
```

Inspect the authenticated user:

```bash
curl http://localhost:8000/auth/me \
  -H "Authorization: Bearer <app-token>"
```

Sync Gmail:

```bash
curl -X POST http://localhost:8000/emails/sync \
  -H "Authorization: Bearer <app-token>"
```

List emails:

```bash
curl http://localhost:8000/emails \
  -H "Authorization: Bearer <app-token>"
```

Apply a safe cleanup action:

```bash
curl -X POST http://localhost:8000/emails/123/execute \
  -H "Authorization: Bearer <app-token>" \
  -H "Content-Type: application/json" \
  -d '{"action":"archive","confirm_high_risk":false}'
```

Apply labels:

```bash
curl -X POST http://localhost:8000/emails/123/execute \
  -H "Authorization: Bearer <app-token>" \
  -H "Content-Type: application/json" \
  -d '{"action":"label","label_names":["Finance","Follow Up"]}'
```

## Test Commands

Backend unit checks used during implementation:

```bash
PYTHONPATH=backend python -m py_compile \
  backend/app/api/auth.py \
  backend/app/api/emails.py \
  backend/app/services/gmail_service.py \
  backend/app/services/recommendation_service.py

cd backend && PYTHONPATH=. pytest -q
```
