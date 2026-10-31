# TalkAor local development

The FastAPI backend is in the repository root. The Next.js frontend is in `ai-calling-frontend/`.

## Run locally against the backend

1. From the repository root, create the backend environment file:

   ```powershell
   Copy-Item .env.example .env
   ```

   Configure `DATABASE_URL` for a local PostgreSQL database before continuing. Set the required production credentials only when deploying; local Resend credentials are not required to start the backend.

2. In a backend terminal at the repository root, apply migrations and start the API:

   ```powershell
   alembic upgrade head
   uvicorn app.main:app --reload --port 8000
   ```

3. In a second terminal, set up and start the frontend:

   ```powershell
   Set-Location ai-calling-frontend
   Copy-Item .env.example .env.local
   npm install
   npm run dev
   ```

   Open `http://localhost:3000`. The frontend defaults to the real backend at `http://127.0.0.1:8000`. Set `NEXT_PUBLIC_API_MODE=mock` in `ai-calling-frontend/.env.local` to use demo data instead; blank or `live` selects the real API.

## Tests

The backend test suite drops and recreates its database schema. Set `TEST_DATABASE_URL` in the process environment to a separate, empty PostgreSQL test database before running tests; the test fixture reads this variable directly rather than loading it from `.env`. For example, in PowerShell:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/ai_calling_test"
```

Never point it at a development or production database.

See [`.env.example`](./.env.example) and [`ai-calling-frontend/README.md`](./ai-calling-frontend/README.md) for configuration details.
