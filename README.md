# CivicPulse AI Engine Lab

CivicPulse is a FastAPI backend and Chrome extension for evidence-grounded fact checking. The extension calls the backend's `/api/fact-check` endpoint; the backend uses Groq and can use Gemini as a fallback.

## Deploy the backend on Vercel

The repository includes a root `main.py` entry point and `requirements.txt`, so Vercel can detect the FastAPI app when you import this GitHub repository as a Python project.

1. Import `https://github.com/aiger079/Civic_Pluse` in Vercel.
2. Before deploying, add these environment variables in the Vercel project settings:
   - `GROQ_API_KEY` — required.
   - `CIVICPULSE_API_KEY` — required; generate a separate strong secret for the deployed service.
   - `GEMINI_API_KEY` — optional fallback provider key.
   - `CIVICPULSE_DATA_DIR=/tmp/civicpulse` — required for this JSON-backed demo to start in Vercel's writable temporary directory.
   - `ALLOWED_ORIGINS=https://civicpluse.naxiv.com` — include each exact website origin that should call the API.
   - `CHROME_EXTENSION_ORIGIN=chrome-extension://<published-extension-id>` — set this to the exact Chrome Web Store extension origin after its ID is known.
3. Add `civicpluse.naxiv.com` as a Vercel domain and configure the DNS records Vercel shows. The extension source currently calls this domain. If you use a `*.vercel.app` URL instead, update the extension API URL and its host permissions before packaging it.
4. Deploy. Vercel will provide an HTTPS URL. Check `/health` and `/` on that URL.

Store provider keys and the admin key in Vercel's Environment Variables settings. Never put them in the extension, source files, or GitHub.

## Demo storage limitation

The backend currently stores claims, incidents, and audit records in JSON files. `/tmp/civicpulse` is temporary on Vercel, so those records can disappear between function instances or deployments. The local `backend/data/*.json` files are excluded from Git because they contain mutable demo records and helper contact details. Use a persistent database before relying on the ledger or moderation data online.

## Chrome extension

The unpacked extension source is in `extension/`. Load that folder through `chrome://extensions` with Developer mode enabled. `CivicPulse-Extension.zip` is the packaged extension archive. The extension needs the deployed backend URL to respond over HTTPS before fact checks will work.

## Local backend

Copy `backend/.env.example` to `backend/.env`, fill in the required keys, then run:

```powershell
python -m pip install -r requirements.txt
python backend/main.py
```

The local backend listens on `http://127.0.0.1:8000` by default.
