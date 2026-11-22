import os
import json
import asyncio
import base64
import hmac
import re
import tempfile
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Literal
from urllib.parse import urlsplit
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Header, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

# Load environment configuration (.env)
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
load_dotenv()

if __package__:
    from .filter_engine import DualGateEngine, ROUTABLE_CAPABILITIES
    from .router import HelperRouter
else:  # Support running this module directly during local development.
    from filter_engine import DualGateEngine, ROUTABLE_CAPABILITIES
    from router import HelperRouter

# CRITICAL SECURITY STOP-SHIP CHECK: Fail fast if secrets are missing from environment
CIVICPULSE_API_KEY = (os.getenv("CIVICPULSE_API_KEY") or "").strip()
if not CIVICPULSE_API_KEY or not CIVICPULSE_API_KEY.strip():
    raise RuntimeError(
        "CRITICAL SECURITY STOP-SHIP: Missing CIVICPULSE_API_KEY environment variable. "
        "Application refuses to start without admin secret."
    )

CLIENT_INGEST_TOKEN = (os.getenv("CLIENT_INGEST_TOKEN") or "").strip() or None

app = FastAPI(title="CivicPulse AI Engine Lab & Ledger")

FACT_CHECK_RATE_LIMIT = 20
FACT_CHECK_RATE_WINDOW_SECONDS = 60
_fact_check_requests = defaultdict(deque)
_fact_check_rate_lock = threading.Lock()


def consume_fact_check_quota(client_id: str, now: Optional[float] = None) -> bool:
    """Allow at most 20 fact-check requests per client during a rolling minute."""
    timestamp = time.monotonic() if now is None else now
    key = client_id or "unknown"
    with _fact_check_rate_lock:
        requests = _fact_check_requests[key]
        cutoff = timestamp - FACT_CHECK_RATE_WINDOW_SECONDS
        while requests and requests[0] <= cutoff:
            requests.popleft()
        if len(requests) >= FACT_CHECK_RATE_LIMIT:
            return False
        requests.append(timestamp)
        if len(_fact_check_requests) > 1024:
            for old_key, old_requests in list(_fact_check_requests.items()):
                if not old_requests or timestamp - old_requests[-1] >= FACT_CHECK_RATE_WINDOW_SECONDS:
                    _fact_check_requests.pop(old_key, None)
        return True

# Base directory for persistent JSON storage. Tests and deployments can isolate data.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.expanduser(
    os.getenv("CIVICPULSE_DATA_DIR") or os.path.join(BASE_DIR, "data")
))
os.makedirs(DATA_DIR, exist_ok=True)

CLAIMS_FILE = os.path.join(DATA_DIR, "claims.json")
INCIDENTS_FILE = os.path.join(DATA_DIR, "incidents.json")
AUDIT_LOG_FILE = os.path.join(DATA_DIR, "audit_log.json")

# Security Configuration: Specific Origins
ALLOWED_ORIGINS_RAW = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173,http://127.0.0.1:5173"
)
ALLOWED_ORIGINS = [orig.strip() for orig in ALLOWED_ORIGINS_RAW.split(",") if orig.strip()]
for allowed_origin in ALLOWED_ORIGINS:
    parsed_origin = urlsplit(allowed_origin)
    if (
        parsed_origin.scheme not in {"http", "https"}
        or not parsed_origin.hostname
        or parsed_origin.path not in ("", "/")
        or parsed_origin.query
        or parsed_origin.fragment
        or parsed_origin.username is not None
        or parsed_origin.password is not None
    ):
        raise RuntimeError("ALLOWED_ORIGINS must contain exact HTTP(S) origins, not wildcard URLs.")
CHROME_EXTENSION_ORIGIN = (os.getenv("CHROME_EXTENSION_ORIGIN") or "").strip()
if CHROME_EXTENSION_ORIGIN:
    parsed_extension_origin = urlsplit(CHROME_EXTENSION_ORIGIN)
    if (
        parsed_extension_origin.scheme != "chrome-extension"
        or not re.fullmatch(r"[a-p]{32}", parsed_extension_origin.netloc)
        or parsed_extension_origin.path
        or parsed_extension_origin.query
        or parsed_extension_origin.fragment
    ):
        raise RuntimeError("CHROME_EXTENSION_ORIGIN must be one exact Chrome extension origin.")
    ALLOWED_ORIGINS.append(CHROME_EXTENSION_ORIGIN)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Authentication dependency for administrative/moderation routes
async def verify_admin_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    if not x_api_key or not hmac.compare_digest(x_api_key.strip(), CIVICPULSE_API_KEY):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Missing or invalid X-API-Key header. Provide valid key in header or dashboard top bar."
        )
    return True

# Authentication dependency for ingestion (Admin key or client token)
async def verify_ingest_auth(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_client_token: Optional[str] = Header(None, alias="X-Client-Token")
):
    is_admin = bool(x_api_key and hmac.compare_digest(x_api_key.strip(), CIVICPULSE_API_KEY))
    is_client = bool(
        x_client_token
        and CLIENT_INGEST_TOKEN
        and hmac.compare_digest(x_client_token.strip(), CLIENT_INGEST_TOKEN)
    )
    if not (is_admin or is_client):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Ingestion requires valid X-API-Key or X-Client-Token header."
        )
    return True

# Initialize AI Engine & Router
engine = DualGateEngine()
router = HelperRouter()

# --- Persistent Storage Helpers ---
def load_claims() -> List[Dict[str, Any]]:
    if os.path.exists(CLAIMS_FILE):
        try:
            with open(CLAIMS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_claims(claims: List[Dict[str, Any]]):
    save_json_atomically(CLAIMS_FILE, claims)

def load_incidents() -> Dict[str, Dict[str, Any]]:
    if os.path.exists(INCIDENTS_FILE):
        try:
            with open(INCIDENTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_incidents(incidents: Dict[str, Dict[str, Any]]):
    save_json_atomically(INCIDENTS_FILE, incidents)


def save_json_atomically(path: str, payload: Any):
    """Write a complete JSON snapshot before replacing the previous file."""
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, temporary_path = tempfile.mkstemp(prefix=".civicpulse-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise


def is_safe_source_url(value: str) -> bool:
    """Accept only absolute HTTPS URLs without credentials or whitespace."""
    if not isinstance(value, str) or not value or any(ch.isspace() for ch in value):
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme.lower() == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not parsed.netloc.endswith(":")
        )
    except ValueError:
        return False

def log_audit(action: str, target_id: str, actor: str, details: str):
    logs = []
    if os.path.exists(AUDIT_LOG_FILE):
        try:
            with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            logs = []
    
    logs.insert(0, {
        "action": action,
        "target_id": target_id,
        "actor": actor,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "details": details
    })
    
    save_json_atomically(AUDIT_LOG_FILE, logs[:200])

# In-memory working copies loaded from disk
claims_db: List[Dict[str, Any]] = load_claims()
incidents_db: Dict[str, Dict[str, Any]] = load_incidents()

# Telemetry tracking
telemetry = {
    "total_messages": 0,
    "fact_checks": 0,
    "fact_check_flags": 0,
    "noise_dropped": 0,
    "toxic_suppressed": 0,
    "rumours_suppressed": 0,
    "pending_reviews": len([inc for inc in incidents_db.values() if inc.get("status") == "DISPATCH_PENDING"]),
    "approved_dispatches": len([inc for inc in incidents_db.values() if inc.get("status") == "DISPATCH_APPROVED"]),
    "review_closures": 0,
}

# WebSocket client connections
connected_clients: set[WebSocket] = set()

# Pydantic Schemas with strict validation and length caps
class ClaimCreateSchema(BaseModel):
    id: Optional[str] = None
    text: str = Field(..., min_length=10, max_length=500)
    category: Literal[
        "utility_flood", "electrical_grid", "medical_emergency",
        "fire_safety", "infrastructure", "general"
    ]
    source_links: List[str] = Field(..., min_length=1)
    verifier_status: Literal["OFFICIALLY_VERIFIED", "COMMUNITY_WITNESSED", "UNCONFIRMED"] = "UNCONFIRMED"
    verifier_identity: str = Field(..., min_length=3, max_length=100)
    witness_count: int = Field(default=1, ge=1, le=1000)

class IngestRequest(BaseModel):
    sender_id: str = Field(..., min_length=3, max_length=50)
    text: str = Field(..., min_length=1, max_length=1000)
    latitude: float = Field(default=28.4595, ge=-90, le=90)
    longitude: float = Field(default=77.0266, ge=-180, le=180)
    dry_run: Optional[bool] = False

class RegressionTestRequest(BaseModel):
    scenario: Literal["exploded", "operational"]
    model_config = {"extra": "forbid"}


REGRESSION_CLAIMS = [
    {
        "id": "regression_fixture_transformer",
        "text": "Transformer at Gate 1 is operational; power restored in Tower C.",
        "status": "ACTIVE",
        "verifier_status": "OFFICIALLY_VERIFIED",
        "source_links": [],
    }
]

class FactCheckRequest(BaseModel):
    text: str = Field(..., min_length=5, max_length=1500)
    context: Optional[str] = Field(default="social_media_selection", max_length=200)

class IncidentReviewAction(BaseModel):
    moderator_notes: str = Field(default="Approved by authenticated admin", min_length=3, max_length=300)

@app.get("/health")
def health():
    return {
        "status": "online",
        "device": engine.device,
        "groq_model": engine.groq_model,
        "human_in_the_loop": True,
        "persistence": "JSON Files",
        "cors_restricted": True,
        "active_claims_count": len([c for c in claims_db if c.get("status", "ACTIVE") == "ACTIVE"]),
        "total_claims_history": len(claims_db)
    }

@app.get("/stats")
def get_stats():
    total = max(1, telemetry["total_messages"])
    noise_reduction_pct = round(
        ((telemetry["noise_dropped"] + telemetry["toxic_suppressed"] + telemetry["rumours_suppressed"]) / total) * 100,
        1
    )
    return {
        **telemetry,
        "noise_reduction_pct": noise_reduction_pct
    }

@app.get("/claims")
def get_claims(include_resolved: bool = Query(True)):
    """Returns claims. Active claims are used for NLI; resolved claims are preserved for history."""
    if include_resolved:
        return claims_db
    return [c for c in claims_db if c.get("status", "ACTIVE") == "ACTIVE"]

@app.post("/claims", dependencies=[Depends(verify_admin_key)])
def add_claim(req: ClaimCreateSchema):
    new_id = req.id or f"claim_{len(claims_db) + 1:02d}"
    if any(claim.get("id") == new_id for claim in claims_db):
        raise HTTPException(status_code=409, detail="Claim ID already exists")
    if any(not is_safe_source_url(url) for url in req.source_links):
        raise HTTPException(status_code=422, detail="Claim sources must be absolute HTTPS URLs")
    now_iso = datetime.now(timezone.utc).isoformat()
    claim = {
        "id": new_id,
        "text": req.text,
        "category": req.category,
        "source_links": req.source_links,
        "timestamp": now_iso,
        "verifier_status": req.verifier_status,
        "verifier_identity": req.verifier_identity,
        "status": "ACTIVE",
        "witness_count": req.witness_count,
        "created_at": now_iso,
        "resolved_at": None
    }
    claims_db.append(claim)
    save_claims(claims_db)
    log_audit("CLAIM_CREATED", new_id, req.verifier_identity, f"Created active claim in category {req.category}")
    return {"status": "success", "claim": claim}

@app.patch("/claims/{claim_id}/resolve", dependencies=[Depends(verify_admin_key)])
def resolve_claim(claim_id: str):
    """
    Marks a claim as RESOLVED.
    Resolved claims are excluded from active NLI matching, but preserved in ledger history.
    """
    claim = next((c for c in claims_db if c["id"] == claim_id), None)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found in ledger")
    
    claim["status"] = "RESOLVED"
    claim["resolved_at"] = datetime.now(timezone.utc).isoformat()
    save_claims(claims_db)
    log_audit("CLAIM_RESOLVED", claim_id, "Admin Moderator", f"Claim resolved; excluded from active matching.")
    return {"status": "resolved", "claim": claim}

@app.delete("/claims/{claim_id}", dependencies=[Depends(verify_admin_key)])
def delete_claim(claim_id: str):
    """Marks a claim as EXPIRED and archives it in history."""
    claim = next((c for c in claims_db if c["id"] == claim_id), None)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found in ledger")
    
    claim["status"] = "EXPIRED"
    save_claims(claims_db)
    log_audit("CLAIM_EXPIRED", claim_id, "Admin Moderator", "Claim expired / archived.")
    return {"status": "expired", "claim_id": claim_id}

@app.get("/audit-log", dependencies=[Depends(verify_admin_key)])
def get_audit_log():
    """Sensitive read route: protected by Admin API Key."""
    if os.path.exists(AUDIT_LOG_FILE):
        try:
            with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

@app.get("/helpers")
def get_helpers():
    """Returns general volunteer registry with phone numbers masked for privacy."""
    all_helpers = router.get_all_helpers()
    safe_helpers = []
    for h in all_helpers:
        safe_h = dict(h)
        phone = safe_h.get("phone", "")
        if len(phone) >= 6:
            safe_h["phone"] = phone[:4] + "****" + phone[-2:]
        safe_helpers.append(safe_h)
    return safe_helpers

@app.get("/incidents/pending", dependencies=[Depends(verify_admin_key)])
def get_pending_incidents():
    """Sensitive read route: protected by Admin API Key."""
    return [inc for inc in incidents_db.values() if inc.get("status") == "DISPATCH_PENDING"]


def incident_dispatch_is_eligible(incident: Dict[str, Any]) -> bool:
    """Fail closed unless an incident is urgent and has a supported capability."""
    return (
        incident.get("dispatch_allowed") is True
        and incident.get("urgency_level") in {"P1", "P2"}
        and incident.get("required_capability") in ROUTABLE_CAPABILITIES
    )

@app.post("/incidents/{incident_id}/approve", dependencies=[Depends(verify_admin_key)])
async def approve_incident(incident_id: str, action: IncidentReviewAction):
    """
    HUMAN APPROVAL REQUIRED:
    Only once approved by a human moderator are volunteers contacted and revealed.
    """
    if incident_id not in incidents_db:
        raise HTTPException(status_code=404, detail="Incident not found in queue")

    inc = incidents_db[incident_id]
    if inc.get("status") != "DISPATCH_PENDING":
        raise HTTPException(status_code=409, detail="Incident is no longer pending review")
    # Legacy incidents without an explicit eligibility flag are fail-closed.
    dispatch_allowed = incident_dispatch_is_eligible(inc)
    inc["dispatch_allowed"] = dispatch_allowed
    inc["status"] = "DISPATCH_APPROVED" if dispatch_allowed else "REVIEW_CLOSED"
    inc["human_approved"] = True
    inc["approved_at"] = datetime.now(timezone.utc).isoformat()
    inc["moderator_notes"] = action.moderator_notes

    # Compute top-5 nearest volunteers
    cap = inc.get("required_capability")
    matched = []
    if dispatch_allowed:
        matched = router.match_helpers(
            incident_lat=inc["latitude"],
            incident_lon=inc["longitude"],
            required_capability=cap,
            top_k=5
        )
    inc["dispatched_helpers"] = matched
    
    save_incidents(incidents_db)
    if dispatch_allowed:
        telemetry["approved_dispatches"] += 1
    else:
        telemetry["review_closures"] += 1
    if telemetry["pending_reviews"] > 0:
        telemetry["pending_reviews"] -= 1

    audit_action = "INCIDENT_APPROVED" if dispatch_allowed else "CONFLICT_REVIEW_CLOSED"
    audit_details = (
        f"Approved dispatch of {len(matched)} helpers. Notes: {action.moderator_notes}"
        if dispatch_allowed
        else f"Closed conflict review without contacting helpers. Notes: {action.moderator_notes}"
    )
    log_audit(audit_action, incident_id, "Authenticated Admin", audit_details)

    # Broadcast approval to connected clients
    payload = {
        "type": "DISPATCH_APPROVED" if dispatch_allowed else "REVIEW_CLOSED",
        "incident": inc
    }
    for ws in list(connected_clients):
        try:
            await ws.send_json(payload)
        except Exception:
            connected_clients.discard(ws)

    return {"status": "success", "incident": inc}

@app.post("/incidents/{incident_id}/reject", dependencies=[Depends(verify_admin_key)])
async def reject_incident(incident_id: str, action: IncidentReviewAction):
    """Human moderator rejects incident."""
    if incident_id not in incidents_db:
        raise HTTPException(status_code=404, detail="Incident not found in queue")

    inc = incidents_db[incident_id]
    if inc.get("status") != "DISPATCH_PENDING":
        raise HTTPException(status_code=409, detail="Incident is no longer pending review")
    dispatch_allowed = incident_dispatch_is_eligible(inc)
    inc["dispatch_allowed"] = dispatch_allowed
    inc["status"] = "DISPATCH_REJECTED" if dispatch_allowed else "REVIEW_REJECTED"
    inc["moderator_notes"] = action.moderator_notes
    save_incidents(incidents_db)
    
    if telemetry["pending_reviews"] > 0:
        telemetry["pending_reviews"] -= 1

    audit_action = "INCIDENT_REJECTED" if dispatch_allowed else "CONFLICT_REVIEW_REJECTED"
    log_audit(audit_action, incident_id, "Authenticated Admin", f"Rejected review. Notes: {action.moderator_notes}")
    return {"status": "rejected", "incident_id": incident_id}

@app.post("/api/fact-check")
def fact_check(req: FactCheckRequest, request: Request):
    """
    Auditable Fact-Check API for students and Chrome Extension.
    Returns a preliminary assessment and labels all model-suggested sources unverified.
    """
    client_id = request.client.host if request.client else "unknown"
    if not consume_fact_check_quota(client_id):
        raise HTTPException(status_code=429, detail="Fact-check request limit exceeded. Try again in a minute.")

    telemetry["fact_checks"] += 1
    result = engine.fact_check_text(req.text, req.context)
    if result.get("falsehood_score", 0) >= 0.65 or result.get("verdict") in ["FABRICATED_HOAX", "DISPUTED_RUMOUR"]:
        telemetry["fact_check_flags"] += 1

    return {
        "query_text": req.text,
        "context": req.context,
        "analysis": result
    }

@app.post("/api/test-regression", dependencies=[Depends(verify_admin_key)])
def run_regression_dry_run(req: RegressionTestRequest):
    """
    Dedicated ISOLATED DRY-RUN regression testing endpoint.
    Evaluates claims without persisting any incidents or polluting the review queue.
    """
    if req.scenario == "exploded":
        text = "Main gate transformer exploded, entire complex will have blackout for next 3 days!"
    else:
        text = "Transformer operational, lights are working fine at Gate 1 and Tower C."

    # Evaluate only against a clearly synthetic fixture, never against the live ledger.
    result = engine.process_message(text, REGRESSION_CLAIMS)
    matched_claim = result.get("matched_claim")
    if matched_claim and matched_claim.get("id") == REGRESSION_CLAIMS[0]["id"]:
        result = {
            **result,
            "matched_claim": {
                **matched_claim,
                "verifier_status": "TEST_FIXTURE",
                "source_links": [],
            },
        }
    return {
        "scenario": req.scenario,
        "text": text,
        "dry_run": True,
        "result": {
            **result,
            "incident_id": None,
            "dispatched_helpers": []
        }
    }

@app.post("/ingest", dependencies=[Depends(verify_ingest_auth)])
async def ingest_message(req: IngestRequest, dry_run: bool = Query(False)):
    """
    Protected Ingestion Route:
    Requires valid X-API-Key or X-Client-Token.
    Supports ?dry_run=true or req.dry_run=true for non-persisted test execution.
    """
    is_dry_run = dry_run or req.dry_run
    if not is_dry_run:
        telemetry["total_messages"] += 1

    result = engine.process_message(req.text, claims_db)

    incident_id = None
    if result["action"] == "NEEDS_REVIEW" and not is_dry_run:
        telemetry["pending_reviews"] += 1
        incident_id = f"inc_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{len(incidents_db)+1}"
        
        cap = result.get("required_capability")
        incident_record = {
            "incident_id": incident_id,
            "text": req.text,
            "sender_id": req.sender_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "DISPATCH_PENDING",
            "human_approved": False,
            "dispatch_allowed": result.get("dispatch_allowed") is True,
            "urgency_level": result.get("urgency_level", "NONE"),
            "required_capability": cap,
            "latitude": req.latitude,
            "longitude": req.longitude,
            "matched_claim": result.get("matched_claim"),
            "entailment_score": result.get("entailment_score"),
            "dispatched_helpers": [] # Hidden until human approval!
        }
        incidents_db[incident_id] = incident_record
        save_incidents(incidents_db)
        log_audit("INCIDENT_QUEUED", incident_id, req.sender_id, f"Queued for human review (Urgency: {result.get('urgency_level')})")
    elif not is_dry_run:
        if result["action"] == "SUPPRESS_TOXIC":
            telemetry["toxic_suppressed"] += 1
        elif result["action"] == "SUPPRESS_PANIC":
            telemetry["rumours_suppressed"] += 1
        elif result["action"] == "NOISE_DROP":
            telemetry["noise_dropped"] += 1

    payload = {
        "sender_id": req.sender_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dry_run": is_dry_run,
        "result": {
            **result,
            "incident_id": incident_id,
            "dispatched_helpers": []
        }
    }

    # Broadcast to connected clients only for real ingests
    if not is_dry_run:
        for ws in list(connected_clients):
            try:
                await ws.send_json(payload)
            except Exception:
                connected_clients.discard(ws)

    return payload

@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    credential = None
    for protocol in websocket.scope.get("subprotocols", []):
        if protocol.startswith("civicpulse-key."):
            encoded = protocol.removeprefix("civicpulse-key.")
            try:
                padded = encoded + ("=" * (-len(encoded) % 4))
                credential = base64.urlsafe_b64decode(padded).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                credential = None
            break

    if not credential or not hmac.compare_digest(credential, CIVICPULSE_API_KEY):
        await websocket.close(code=1008, reason="Admin authentication required")
        return

    await websocket.accept(subprotocol="civicpulse-admin")
    connected_clients.add(websocket)
    try:
        await websocket.send_json({
            "type": "HANDSHAKE",
            "stats": get_stats(),
            "active_claims": [c for c in claims_db if c.get("status", "ACTIVE") == "ACTIVE"],
            "pending_incidents": [inc for inc in incidents_db.values() if inc.get("status") == "DISPATCH_PENDING"]
        })
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        connected_clients.discard(websocket)

# Static files for testing frontend
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def serve_landing_page():
    landing_file = os.path.join(static_dir, "landing.html")
    if os.path.exists(landing_file):
        return FileResponse(landing_file)
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "CivicPulse AI Engine Online. Access /health."}

@app.get("/app")
def serve_fact_checker():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    raise HTTPException(status_code=404, detail="Fact-checking workspace is unavailable.")

@app.get("/extension/download")
def download_chrome_extension():
    archive_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "CivicPulse-Extension.zip")
    if os.path.exists(archive_file):
        return FileResponse(archive_file, media_type="application/zip", filename="CivicPulse-Extension.zip")
    raise HTTPException(status_code=404, detail="The Chrome extension package is unavailable.")

# Restrict network access: Bind strictly to 127.0.0.1 (localhost) by default
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
