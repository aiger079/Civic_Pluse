# CivicPulse AI Engine Lab

CivicPulse is a FastAPI backend and Chrome extension for evidence-grounded fact checking. The extension calls the backend's `/api/fact-check` endpoint. OpenRouter can provide the AI model for fact-check assessments and other AI-assisted triage tasks; Tavily supplies independently retrieved live web results for manual checks. Gemini and Groq remain optional providers when explicitly selected.

## Deploy the backend on Vercel

The repository includes a root `main.py` entry point and `requirements.txt`, so Vercel can detect the FastAPI app when you import this GitHub repository as a Python project.

1. Import `https://github.com/aiger079/Civic_Pluse` in Vercel.
2. Before deploying, add these environment variables in the Vercel project settings:
   - `OPENROUTER_API_KEY` — required when using OpenRouter.
   - `CIVICPULSE_AI_PROVIDER=openrouter` — selects OpenRouter for model tasks.
   - `CIVICPULSE_FACT_CHECK_PROVIDER=openrouter` — selects OpenRouter plus Tavily for manual web-grounded checks.
   - `OPENROUTER_MODEL=openrouter/free` — routes to an available free model supporting the request format. Free model quotas still apply; choose a paid model explicitly if you need higher availability.
   - `TAVILY_API_KEY` — recommended for reliable web/news search quota; without it, keyless Tavily access is rate limited.
   - `GEMINI_API_KEY` / `GROQ_API_KEY` — optional only if you select those providers instead.
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

OpenRouter provides the language model; it does not itself guarantee web search. For manual web/news checks, CivicPulse asks the selected AI provider for a focused public query, retrieves results through Tavily, then asks the model to assess only those returned excerpts. Tavily receives the query without the current site domain. Keyless Tavily access is rate limited, so set `TAVILY_API_KEY` as a server environment secret for a dedicated quota. Automatic scanning uses the configured search-capable fact-check provider; the OpenRouter plus Tavily path is enabled for manual checks.

## Live search

Live web search is disabled by default through `CIVICPULSE_LIVE_SEARCH_ENABLED=false`. In this mode CivicPulse does not send claims to Gemini Search, Groq browser search, Tavily, or Wikipedia and returns `LIVE_SEARCH_DISABLED` for fact checks. Set the variable to `true` only when online evidence retrieval is intentionally required.

## Local backend

Copy `backend/.env.example` to `backend/.env`, fill in the required keys, then run:

```powershell
python -m pip install -r requirements.txt
python backend/main.py
```

The local backend listens on `http://127.0.0.1:8000` by default.
