# Budget Bazzar

A small personal-finance dashboard built with a separated Flask backend and vanilla JavaScript frontend.

## Project structure

- `backend/app.py` - Flask API, authentication, sessions, and SQLite access.
- `frontend/templates/` - login and dashboard HTML templates.
- `frontend/static/` - browser JavaScript and CSS.
- `app.py` - compatibility launcher for local development.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

Open `http://127.0.0.1:5000` and enter the value of `BUDGET_BAZZAR_API_KEY` from `.env`.

API requests must include the `X-API-Key` header. For example:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/health -Headers @{'X-API-Key'='dev-budget-bazzar-key'}
```

Change the development key before sharing or deploying the app. The SQLite database is created automatically on first run.

## Publish online

This project includes `render.yaml` for Render deployment:

1. Push this folder to a GitHub repository.
2. In Render, choose **New +** -> **Blueprint** and select the repository.
3. Set `BUDGET_BAZZAR_API_KEY` in the Render environment settings.
4. Deploy. Render will provide a public `onrender.com` URL that works on any device.

The included persistent disk keeps the SQLite accounts and transactions between deploys. Never commit `.env` or place real secrets in frontend files.
