# Open Source Assist — System Documentation

Welcome to the comprehensive technical documentation for **Open Source Assist** — an intelligent, full-stack platform designed to accelerate open-source discovery, developer mentorship, skill assessment, and community collaboration.

The platform combines an asynchronous **FastAPI** backend with local **Qdrant Vector Database** indexing, **Google Gemini 3.5 Flash** (via LiteLLM & LangGraph), and a responsive **React + TypeScript + Vite** frontend.

## ⚡ Quick Start

To start all services (PostgreSQL schema check, FastAPI backend, and Vite frontend) with a single command:

**Windows (PowerShell):**
```powershell
.\start.ps1
```

**Windows (Command Prompt / Double Click):**
```cmd
start.bat
```

To stop all running services:
```powershell
.\stop.ps1
# or
stop.bat
```

Services started:
* **Frontend UI**: [http://localhost:5173](http://localhost:5173)
* **Backend API & Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **Backend Health**: [http://localhost:8000/health](http://localhost:8000/health)

### 🔧 First-time setup (required before sign-in / sign-up works)

The backend needs a reachable database, SMTP credentials, and (optionally) a GitHub OAuth App. Configure these in `.env`, then **restart the backend** — settings are loaded at startup, so `.env` edits never apply to a running server.

1. **Database** — pick one:
   - Local (recommended for first run): `docker compose up -d postgres`, then `alembic upgrade head`
   - Existing instance (e.g. AWS RDS): set `DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname`
   - A wrong or unreachable `DATABASE_URL` makes **both** sign-in and sign-up fail — the API now reports this as a 503 "database" error instead of blaming your network.
2. **Email (SMTP)** — `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `MAIL_FROM`. Sign-up and password-reset emails cannot be sent without these. For Gmail, use an *App Password* (not your account password) and set `MAIL_FROM` to the same address as `SMTP_USERNAME`.
3. **GitHub sign-in (optional)** — create an OAuth App at *GitHub → Settings → Developer settings → OAuth Apps → New OAuth App*:
   - Homepage URL: `http://localhost:5173` (or your production domain)
   - Set `GITHUB_REDIRECT_URI` to the full callback URL and enter that exact same URL in the OAuth App's **Authorization callback URL**. Locally this is `http://localhost:5173/api/v1/auth/github/callback`; in production it must be the publicly reachable callback route (and `/api` must be routed to the backend).
   - Set `FRONTEND_URL` to the frontend origin so the callback can return the user to the site.
   - Put the Client ID / Client Secret into `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET`. Until then, the "Continue with GitHub" button is disabled with an explanatory note.
4. **GitHub data (optional)** — set `GITHUB_TOKEN` (a fine-grained PAT) to enable the dashboard's GitHub stats, activity feeds, and rewards sync.

---

## 📚 Documentation Index

| Document | Description |
| :--- | :--- |
| **[1. System Architecture (End-to-End)](ARCHITECTURE.md)** | Full-stack platform architecture, component topology, LangGraph AI workflows, Airflow DAGs, and database ER schemas. |
| **[2. Search Module Architecture](doc/search_module/architecture.md)** | Subsystem architecture, separation of concerns, concurrency model, Python GIL avoidance, and Qdrant Server topology. |
| **[3. Search & Ranking Engine](doc/search_module/search_and_ranking.md)** | Mathematical formulation of semantic similarity, logarithmic popularity normalization, and the Strategy pattern. |
| **[4. Teammate Integration Guide](doc/integration/search_integration_backend.md)** | Integration guide for teammate modules (Ingestion, RAG, and Auth hooks). |
| **[5. Deployment & Operations](doc/deployment_and_operations.md)** | Docker Compose configuration, Qdrant Cloud deployment, environment configuration, database seeding, and testing with `uv`. |
| **[6. API Contract & Changelog](API_CONTRACT.md)** | Formal versioned API contracts, HTTP endpoints, status codes, and request/response JSON schemas. |
| **[7. Database Design & Schemas](doc/database_design.md)** | Complete PostgreSQL relational ER diagrams, constraints reference, and Qdrant vector database topology. |

---

## 🚀 Platform Capabilities

* **Dual-Tier Semantic & Hybrid Search**:
  * Dense semantic vector retrieval over indexed open-source repositories using local 384-dimensional ONNX embeddings (`BAAI/bge-small-en-v1.5`).
  * Logarithmic popularity dampening and **Multiplicative Gate** re-ranking ($\text{FinalScore} = S_{\text{semantic}} \times [1 + \alpha \cdot P_{\text{popularity}}]$).
  * Seamless fallback from live GitHub Search API (OAuth users) to local Qdrant vectors (guest users).
* **Personalized AI Roadmaps & Skill Assessments**:
  * Dynamic GitHub-grounded MCQ and subjective question generation.
  * Automated scoring and context synthesis powered by Google Gemini via LangGraph.
  * Interactive roadmap step progression and milestone tracking.
* **Community Events & Admin Management**:
  * Event calendar for upcoming open-source meetups, conferences, and hackathons.
  * Dedicated administrator panel for scheduling, editing, and managing events.
* **Projects & Contributor Ecosystem**:
  * Curated directory of trending open-source projects.
  * Contributor discovery with avatars, GitHub activity stats, and commit counts.
* **Skill-Aware AI Mentorship & Discussions**:
  * AI chatbot calibrated to individual developer experience levels.
  * Community discussion forum with threaded replies and admin moderation.

---

## 🔐 Authentication & Security

The backend provides comprehensive PostgreSQL-backed authentication and authorization:

* **Email & Password**:
  * `POST /api/v1/auth/signup` (Dispatches 6-digit OTP via SMTP)
  * `POST /api/v1/auth/verify-signup-otp` (Validates OTP and registers user)
  * `POST /api/v1/auth/login` (Returns Bearer JWT) — pass `"remember_me": true` for a 1-day session (default: 2 hours); the response includes the token's `expires_at`
  * `POST /api/v1/auth/forgot-password` & `POST /api/v1/auth/reset-password`
  * `GET /api/v1/auth/me` (Current user profile and permissions)
* **GitHub OAuth**:
  * `GET /api/v1/auth/github/url`
  * `GET /api/v1/auth/github/callback` & `POST /api/v1/auth/github/callback`
  * `POST /api/v1/auth/github/pat-login` (Development fallback)
* **Email Delivery**:
  * Built using `aiosmtplib` in [`backend/services/mail_service.py`](backend/services/mail_service.py) supporting STARTTLS and SSL.

Copy `.env.example` to `.env`, then configure the database either by setting
`DATABASE_URL` (a full async SQLAlchemy URL, e.g.
`postgresql+asyncpg://user:pass@host:5432/dbname`) or by filling in the
individual `POSTGRES_*` fields — and set a long random `JWT_SECRET_KEY`.
Apply the schema migrations with:

```powershell
uv run alembic upgrade head
uv run uvicorn backend.main:app --reload
```

Reset codes expire after five minutes, are persisted as HMAC digests, and are single-use. Email delivery is handled by `backend/services/mail_service.py` (set `SMTP_*` variables to enable real delivery; without credentials it logs instead of sending).

## 🎁 Rewards System

Users earn redeemable points for real activity, tracked in an append-only `reward_ledger` table
(apply `uv run alembic upgrade head` to create it):

* **GitHub activity** — `POST /api/v1/rewards/sync-github` replays the user's recent public events:
  commits (+5), opened pull requests (+25), merged pull requests (+50), issues (+10), reviews (+15),
  stars (+2), forks (+5). Idempotent per GitHub event, so syncing again only credits new activity.
* **Learning modules** — finishing a guided tutorial credits +20 via
  `POST /api/v1/rewards/tutorial-completed`; completing a roadmap step credits +30, with a +100
  bonus when the whole roadmap is finished (both wired into the roadmap progress endpoints).
* **Redeeming** — `POST /api/v1/rewards/redeem` spends points on 1:1 mentor sessions
  (beginner 100 / intermediate 300 / advanced 600 / expert 1000 pts); cancelling a booking refunds
  the points. The dashboard Redeem section is fully wired to this API.

Full endpoint contracts live in `API_CONTRACT.md` (v0.5.0).

## 🧪 Development & Testing

Run the backend test suite (54 tests, no external services required — the suite
uses an isolated file-backed SQLite database):

```powershell
uv run pytest backend/tests
```

Frontend checks:

```powershell
cd frontend
npm run typecheck
npm run build
```

### Manual setup (all platforms)

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 20+, and Docker (for Qdrant).

```bash
# 1. Start Qdrant (vector database)
docker compose up -d

# 2. Configure environment
cp .env.example .env   # then edit DATABASE_URL / POSTGRES_* and JWT_SECRET_KEY

# 3. Install dependencies and apply migrations
uv sync
uv run alembic upgrade head

# 4. Run backend and frontend (in separate terminals)
uv run uvicorn backend.main:app --reload
cd frontend && npm install && npm run dev
```
