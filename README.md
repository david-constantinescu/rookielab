# RookieLab — Interactive Lessons & Simulations (Flask)

A small Flask-based web application to host lessons, interactive lessons (with CAD viewer support), downloadable simulations, and simple user management via Auth0. It includes PDF generation for lessons, a Gemini AI chat proxy for lesson Q&A, quiz functionality, and integration with a cloud-hosted SQLite-like service (`sqlitecloud`).

This README documents how to run the project locally, environment variables required, Docker usage, project structure, and developer notes for extending the app.

## Features
- Serve static lessons and interactive lessons with optional CAD files and quizzes
- Admin area (Auth0-protected) to add lessons, interactive lessons and simulations
- Generate and download lesson PDFs (server-side via FPDF)
- Preview first page of remote PDF simulations as images for unauthenticated users
- Quiz API endpoints and quiz result persistence
- Gemini AI integration to provide contextual chat responses based on lesson content
- CAD proxy endpoint to allow 3dviewer.net or other clients to fetch CAD files with correct CORS headers

## Quick demo
The app runs a Flask server on port 2014 by default when executed directly. Admin actions require Auth0 authentication and membership in the admin emails configured within the app logic.

## Requirements
- Python 3.9+ (recommend 3.10 or 3.11)
- poppler-utils installed on the host (required by `pdf2image` for PDF conversion)

Python dependencies are listed in `requirements.txt`. Key packages used:
- flask
- authlib
- requests
- fpdf
- pdf2image
- sqlitecloud
- google-generativeai
- python-dotenv

Install system dependency on macOS (Homebrew):

```bash
# Install poppler for pdf2image
brew install poppler
```

Install Python dependencies:

```bash
python3 -m pip install -r requirements.txt
```

## Environment variables
Create a `.env` file in the project root (or set the variables in your environment). The app reads configuration from environment variables. The following are used by the app:

- FLASK_SECRET_KEY — secret key for Flask sessions (required)
- AUTH0_CLIENT_ID — Auth0 application client ID
- AUTH0_CLIENT_SECRET — Auth0 application client secret
- AUTH0_DOMAIN — Auth0 tenant domain (example: your-tenant.us.auth0.com)
- AUTH0_CALLBACK_URL — Redirect URL configured in Auth0 (e.g., http://localhost:2014/callback)
- API_AUDIENCE — Auth0 API audience (used when validating tokens)
- ISSUER — Token issuer URL for JWT validation
- ALGORITHMS — JWT algorithm(s) (default RS256)
- GEMINI_API_KEY — API key for Google Gemini (used by `google-generativeai` integration)

Example `.env` snippet:

```ini
FLASK_SECRET_KEY=change-me
AUTH0_CLIENT_ID=your_auth0_client_id
AUTH0_CLIENT_SECRET=your_auth0_client_secret
AUTH0_DOMAIN=your-domain.auth0.com
AUTH0_CALLBACK_URL=http://localhost:2014/callback
API_AUDIENCE=your-api-audience
ISSUER=https://your-domain.auth0.com/
ALGORITHMS=RS256
GEMINI_API_KEY=your_gemini_api_key
```

Do not commit secret keys to version control.

## Running locally
1. Ensure dependencies are installed and `.env` is configured.
2. Initialize the DB and start the app by running:

```bash
python3 app.py
```

The app listens on 0.0.0.0:2014 by default. Visit http://localhost:2014/ to open the site.

If you prefer a production WSGI server, use `gunicorn`:

```bash
gunicorn --bind 0.0.0.0:2014 app:app
```

## Docker
This repository contains a `Dockerfile` for containerizing the app. The image expects environment variables to be supplied at runtime.

Build the image:

```bash
docker build -t noname-app .
```

Run the container (example):

```bash
docker run -p 2014:2014 \
	-e FLASK_SECRET_KEY=change-me \
	-e AUTH0_CLIENT_ID=... \
	-e AUTH0_CLIENT_SECRET=... \
	-e AUTH0_DOMAIN=... \
	-e AUTH0_CALLBACK_URL=http://localhost:2014/callback \
	-e API_AUDIENCE=... \
	-e ISSUER=... \
	-e GEMINI_API_KEY=... \
	noname-app
```

Adjust environment variables and volumes as needed (e.g., to persist uploaded files).

## Project structure

Top-level files and directories (important ones):

- `app.py` — main Flask application (routes, DB init, AI/chat, PDF generation)
- `requirements.txt` — Python dependencies
- `Dockerfile` — container image instructions
- `static/` — CSS, JS, images and generated PDFs
- `templates/` — Jinja2 HTML templates for pages
- `.env` — environment variables (not committed)

Templates include pages for home, account, lessons, interactive lessons, admin panels, policies, and more.

## Admin & Authentication
Authentication is handled via Auth0. The `/login` route redirects to Auth0 and `/callback` handles the token and session setup. The app marks certain emails as admin (configured in code; see `app.py`) — update that logic if you need dynamic admin configuration.

Important admin routes:
- `/admin` — general admin dashboard
- `/admin/lessons` — add lessons
- `/admin/interactive-lessons` — add interactive lessons

Only signed-in users with admin flag can access these routes.

## API endpoints
- `GET /api/quiz/<lesson_id>` — returns quiz data for an interactive lesson
- `POST /api/submit-quiz` — submit quiz results (requires authentication)
- `GET /api/cad-proxy/<lesson_id>` — proxy CAD file (adds permissive CORS headers)
- `GET /api/cad-url/<lesson_id>` — returns CAD file URL for a lesson
- `POST /api/chat-with-gemini` — proxy to Gemini AI for contextual Q&A

## Notes on external services
- sqlitecloud: this app connects to a SQLite-like cloud-hosted DB. The connection string is present in `app.py`. If you plan to run locally without the cloud DB, replace `get_db()` and `init_db()` with a local SQLite file connection or update the connection string.
- Gemini (google-generativeai) requires an API key and may incur usage costs.

## Development notes & suggestions
- Replace hardcoded admin email checks in `app.py` with a proper role-based admin table or an Auth0 RBAC/claim.
- Secrets should be stored securely (Vault, AWS Secrets Manager, or GitHub Actions secrets for CI) in production.
- Add unit tests for key routes and the API (use `pytest` and Flask test client).
- Consider using Flask-Migrate and SQLAlchemy for richer DB migrations and models vs. raw SQL.

## Contributing
Contributions are welcome. For non-trivial changes, open an issue first to discuss. Keep changes small and provide tests where appropriate.

## License
See `LICENSE` at the repository root for license terms.

## Contact
If you need help setting up the project or want to contribute, open an issue or contact the repository owners.

---

Last updated: 2025-10-19
