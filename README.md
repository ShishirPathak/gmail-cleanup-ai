# Gmail Cleanup AI

Gmail Cleanup AI is a review-first inbox triage system that combines deterministic safety rules, embedding-based similarity, and optional LLM fallback to recommend safe cleanup actions on Gmail messages.

The project is intentionally designed around a conservative operating model:
- protect high-risk email before optimizing for cleanup
- explain why an email is being recommended for archive, keep, or review
- keep the user in the loop before applying Gmail actions

The current implementation includes a FastAPI backend, PostgreSQL with `pgvector`, Redis, Google OAuth + Gmail integration, and a React/Vite review interface. It also includes a non-production demo inbox flow for validating the recommendation pipeline without connecting a real mailbox.

## Product Direction

This is not a blind “delete my inbox” tool. The system is built around safe triage:
- deterministic policy protects OTP, banking, travel, interview, invoice, receipt, and other important messages
- vector similarity learns from prior email patterns and user actions
- an LLM is used only for low-confidence classifications when enabled
- archive/trash remain guarded actions, not unconditional automation

That architecture is deliberate. Email cleanup is high-cost when wrong. The repo optimizes for inspectability and operational safety over aggressive automation.

## Core Capabilities

- Google OAuth sign-in and Gmail account linking
- Encrypted access/refresh token storage
- Gmail sync into PostgreSQL without duplicate message creation
- Embedding generation through an OpenAI-compatible interface
- `pgvector` similarity search over stored emails
- Hybrid recommendation logic:
  - rules first
  - similarity/history next
  - optional LLM fallback for ambiguous cases
- Gmail actions:
  - archive
  - trash
  - mark as read
  - apply labels
- Review-first UI:
  - inbox queue
  - detailed email view
  - recommendation source visibility
  - similar email context
  - action history
- Demo inbox mode for non-production testing
- Manual review-and-archive flow for recommended archive candidates

## Safety Model

The safety posture is one of the most important parts of the system.

- High-risk email is identified using explicit rules over sender, domain, subject, and snippet content.
- Important categories are forced toward `keep` even if other signals are noisy.
- Archive and trash are blocked for high-risk emails unless `confirm_high_risk=true` is explicitly provided.
- There is no permanent delete endpoint.
- Demo-mode emails can simulate actions locally in non-production mode without requiring a live Gmail account.

This is why the system can legitimately claim “AI-assisted” without turning the LLM into the sole authority for destructive actions.

## Recommendation Pipeline

At a high level, recommendation generation works like this:

1. Sync or seed an email into the local store.
2. Build a compact embedding text representation from sender, subject, snippet, labels, and unsubscribe signal.
3. Generate an embedding and store it with the email.
4. Run policy classification:
   - explicit risk/protection rules
   - low-risk promotional heuristics
5. Retrieve similar emails using `pgvector`.
6. If user behavior on similar emails is strong enough, bias the recommendation with history.
7. If the resulting recommendation is still low-confidence and LLM is enabled, call the LLM.
8. Apply final guardrail overrides before exposing the recommendation to the UI.

This gives the system three distinct recommendation sources:
- `rule`
- `hybrid`
- `llm`

Those sources are surfaced in the UI so the decision path is inspectable.

## Architecture

### Backend

- `backend/app/api`
  FastAPI routes for auth, health, email sync, email detail, archive review candidates, similarity, and cleanup actions.

- `backend/app/services`
  Gmail OAuth/API integration, account/token handling, Gmail message parsing, embedding providers, similarity search, recommendation policy, and optional LLM classification.

- `backend/app/models`
  SQLAlchemy models for users, Gmail accounts, emails, embeddings, classifications, and user actions.

- `backend/app/db`
  Database session management and Redis access.

- `backend/alembic`
  Schema migration scaffolding.

### Frontend

- `frontend/src/App.jsx`
  Main application shell, landing page, inbox review experience, demo flow, and archive review modal.

- `frontend/src/styles.css`
  Application styling for both signed-out and signed-in experiences.

### Infrastructure

- PostgreSQL 16 + `pgvector`
- Redis 7
- Docker Compose for local orchestration

## Repository Layout

```text
.
├── backend
│   ├── app
│   │   ├── api
│   │   ├── core
│   │   ├── db
│   │   ├── models
│   │   ├── schemas
│   │   ├── services
│   │   └── workers
│   ├── alembic
│   ├── tests
│   └── Dockerfile
├── frontend
│   ├── src
│   └── Dockerfile
└── docker-compose.yml
```

## Running Locally

### 1. Configure environment

Backend variables live in `backend/.env.example`.

Create the real file:

```bash
cp backend/.env.example backend/.env
```

Frontend variables live in `frontend/.env.example`.

Create the real file:

```bash
cp frontend/.env.example frontend/.env
```

### 2. Required backend configuration

Minimum required:

- `SECRET_KEY`
- `DATABASE_URL`
- `REDIS_URL`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`

To enable embeddings through OpenAI-compatible APIs:

- `EMBEDDING_PROVIDER=openai`
- `EMBEDDING_MODEL=text-embedding-3-small`
- `EMBEDDING_API_KEY=...`

To enable LLM fallback:

- `LLM_PROVIDER=openai`
- `LLM_MODEL=...`
- `LLM_API_KEY=...`

The code defaults `EMBEDDING_BASE_URL` and `LLM_BASE_URL` to `https://api.openai.com/v1`, so those usually do not need to be overridden when using OpenAI directly.

### 3. Google OAuth configuration

Set the Google OAuth redirect URI to:

```text
http://localhost:8000/auth/google/callback
```

### 4. Start the stack

From the repository root:

```bash
docker compose up --build -d
```

### 5. Local endpoints

- Frontend: `http://localhost:5173`
- API: `http://localhost:8000`
- Health: `http://localhost:8000/health`

## Demo Mode

The project includes a non-production demo flow so the recommendation engine can be exercised without a real Gmail account.

Demo mode supports:
- temporary demo login
- seeding sample inbox emails
- rule/hybrid/LLM recommendation validation
- simulated archive behavior for demo emails

This is intentionally gated to non-production behavior.

## API Surface

Representative endpoints:

### Auth

- `GET /auth/google/login`
- `GET /auth/google/callback`
- `GET /auth/me`
- `POST /auth/dev-login` (non-production demo flow)

### Email ingestion and review

- `POST /emails/sync`
- `POST /emails/dev-seed`
- `GET /emails/`
- `GET /emails/{email_id}`
- `GET /emails/{email_id}/similar`
- `GET /emails/{email_id}/actions`

### Recommendation-driven bulk review

- `GET /emails/archive-candidates`
- `POST /emails/archive-candidates/archive`

### Manual actions

- `POST /emails/{email_id}/execute`
- `POST /emails/{email_id}/actions`

## Example Requests

Get the Google login URL:

```bash
curl http://localhost:8000/auth/google/login
```

Get the authenticated user:

```bash
curl http://localhost:8000/auth/me \
  -H "Authorization: Bearer <app-token>"
```

Sync Gmail:

```bash
curl -X POST http://localhost:8000/emails/sync \
  -H "Authorization: Bearer <app-token>"
```

List inbox emails:

```bash
curl http://localhost:8000/emails/ \
  -H "Authorization: Bearer <app-token>"
```

Archive one email:

```bash
curl -X POST http://localhost:8000/emails/123/execute \
  -H "Authorization: Bearer <app-token>" \
  -H "Content-Type: application/json" \
  -d '{"action":"archive","confirm_high_risk":false}'
```

Get reviewable archive candidates:

```bash
curl http://localhost:8000/emails/archive-candidates \
  -H "Authorization: Bearer <app-token>"
```

Archive reviewed candidates:

```bash
curl -X POST http://localhost:8000/emails/archive-candidates/archive \
  -H "Authorization: Bearer <app-token>" \
  -H "Content-Type: application/json" \
  -d '{"email_ids":[101,102,103]}'
```

## Migrations and Schema Notes

Run Alembic from `backend/`:

```bash
alembic upgrade head
```

The application also includes startup-time schema compatibility adjustments for local/containerized iteration. That keeps development friction low, but the long-term production-grade direction should be migration-first rather than startup-patch-first.

## Testing

Backend unit tests:

```bash
cd backend && PYTHONPATH=. pytest -q
```

Targeted syntax/compile checks used during implementation:

```bash
PYTHONPATH=backend python -m py_compile \
  backend/app/api/auth.py \
  backend/app/api/emails.py \
  backend/app/services/gmail_service.py \
  backend/app/services/recommendation_service.py
```

Frontend build verification:

```bash
cd frontend && npm run build
```

## Current Engineering Notes

What is already strong:
- recommendation pipeline composition
- Gmail integration and token handling
- safety-oriented action model
- demoability without real mailbox dependency
- visible recommendation source attribution in the UI

What is intentionally still iterative:
- background job execution for sync/automation
- production-grade observability
- deeper API integration testing
- more advanced archive-review selection controls
- finer-grained user automation settings

## Positioning

This repository should be read as a conservative AI product implementation, not a thin wrapper around an LLM.

The system combines:
- policy engineering
- retrieval/similarity over email history
- optional LLM fallback
- UX-level review controls
- Gmail action safety constraints

That combination is the point of the project.
