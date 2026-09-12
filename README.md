# InsightFlow — AI Data Analyst Agent

A complete end-to-end portfolio project based on the supplied AI Data Analyst Agent concept.

## Features

- Premium landing page + responsive analyst workspace
- CSV upload (25 MB demo limit)
- Demo sales dataset generator
- Dataset schema + preview
- Natural-language analysis
- Optional OpenAI-powered SQL/analysis planning, with a local heuristic fallback
- Read-only SQL guardrails
- Interactive bar/line/pie charts
- Generated SQL visibility
- SQL console for advanced users
- Conversation history
- Dataset deletion
- Optional SQLAlchemy database connection test for trusted PostgreSQL/MySQL/SQLite URLs
- Docker Compose setup

## Quick start (Ubuntu/Windows/macOS)

### 1. Requirements

- Python 3.11+ (3.12 recommended)
- Node.js 20+ (22 recommended)
- npm

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Backend: http://localhost:8000  
API docs: http://localhost:8000/docs

### 3. Frontend

Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

### 4. Try it

1. Click **Load demo**.
2. Ask: `Show total revenue by product`.
3. Try the Data preview, History and SQL console tabs.
4. Upload your own CSV.

### 5. Enable real AI planning

Put your API key in `backend/.env`:

```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4.1-mini
```

Restart the backend. Without an API key, the app still runs and uses a local deterministic planner for common analytics questions.

## Docker

```bash
cp backend/.env.example backend/.env
# optionally edit backend/.env and add OPENAI_API_KEY

docker compose up --build
```

Then open http://localhost:5173

## Example questions

- Show total revenue by product
- What is the average profit?
- Show the top 5 products by revenue
- Show revenue trend over time
- Count records by region

## Production roadmap

For a production deployment, add authentication, user-scoped datasets, object storage, background jobs/queues, persistent Postgres metadata, secrets management, query timeouts, row limits, audit logs, and a formal policy for outbound DB connections.
