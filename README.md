# CivicPulse AI Engine Lab

CivicPulse is a FastAPI backend and Chrome extension for evidence-grounded fact checking. The extension calls the backend's `/api/fact-check` endpoint; Gemini can run as the primary provider for live search and the other AI-assisted triage tasks. When Gemini is selected, Groq is ignored even if a legacy Groq secret remains stored.

## Deploy the backend on Vercel

The repository includes a root `main.py` entry point and `requirements.txt`, so Vercel can detect the FastAPI app when you import this GitHub repository as a Python project.

1. Import `https://github.com/aiger079/Civic_Pluse` in Vercel.
2. Before deploying, add these environment variables in the Vercel project settings:
   - `GEMINI_API_KEY` — required when `CIVICPULSE_FACT_CHECK_PROVIDER=gemini`.
   - `CIVICPULSE_FACT_CHECK_PROVIDER=gemini` — selects Gemini Search as the primary fact-check provider.
   - `GROQ_API_KEY` — optional; ignored when Gemini is selected.
   - `CIVICPULSE_API_KEY` — required; generate a separate strong secret for the deployed service.
   - `CIVICPULSE_DATA_DIR=/tmp/civicpulse` — required for this JSON-backed demo to start in Vercel's writable temporary directory.
   - `ALLOWED_ORIGINS=https://civic-pluse-sooty.vercel.app` — include each exact website origin that should call the API.
   - `CHROME_EXTENSION_ORIGIN=chrome-extension://<published-extension-id>` — set this to the exact Chrome Web Store extension origin after its ID is known.
3. The extension source uses `https://civic-pluse-sooty.vercel.app`. If you add a custom domain later, update the API URL, host permissions, and allowed origin before packaging.
4. Deploy. Vercel will provide an HTTPS URL. Check `/health` for service status, `/` for the landing page, and `/app` for the fact-checking workspace.

Store provider keys and the admin key in Vercel's Environment Variables settings. Never put them in the extension, source files, or GitHub.

## Demo storage limitation

The backend currently stores claims, incidents, and audit records in JSON files. `/tmp/civicpulse` is temporary on Vercel, so those records can disappear between function instances or deployments. The local `backend/data/*.json` files are excluded from Git because they contain mutable demo records and helper contact details. Use a persistent database before relying on the ledger or moderation data online.

## Chrome extension

The unpacked extension source is in `extension/`. The landing page links to `CivicPulse-Extension.zip` at `/extension/download`. The Chrome Web Store listing is not published yet, so install the downloaded archive manually: extract it, open `chrome://extensions`, enable Developer mode, then choose **Load unpacked** and select the extracted extension folder. The extension uses the deployed backend URL `https://civic-pluse-sooty.vercel.app` and needs its `/health` endpoint to respond over HTTPS before checks will work.

Automatic visible-claim scanning is enabled by default. It sends only visible text snippets and the current site domain to the backend, checks at a limited pace, and marks claims red only when live search returned sources and the assessment verdict is `FABRICATED_HOAX` or `DISPUTED_RUMOUR`. This is a preliminary AI flag, not a confirmed fact; users can disable automatic scanning in the popup.

Google Search grounding with Gemini 3.8 Flash requires a Gemini project with eligible billing and available search quota. When Google Search fails or returns no usable sources, a manual check in extension 1.2.2 can use Tavily to search the web and Gemini to assess the returned excerpts. Tavily receives a short query about the public claim without the current site domain. Keyless Tavily access is rate limited. Set `TAVILY_API_KEY` as a server environment secret for a dedicated quota. If Tavily is unavailable, manual checks can still use Wikipedia for public encyclopedia topics. Automatic scanning uses the configured Gemini or Groq search provider.

## Local backend

Copy `backend/.env.example` to `backend/.env`, fill in the required keys, then run:

```powershell
python -m pip install -r requirements.txt
python backend/main.py
```

The local backend listens on `http://127.0.0.1:8000` by default.
