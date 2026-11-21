import unittest
import sys
import os
import json
import atexit
import shutil
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from fastapi.testclient import TestClient

# The API tests must never read or overwrite the developer's real incident ledger.
TEST_DATA_DIR = tempfile.mkdtemp(prefix="civicpulse-api-tests-")
os.environ["CIVICPULSE_DATA_DIR"] = TEST_DATA_DIR
atexit.register(shutil.rmtree, TEST_DATA_DIR, ignore_errors=True)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main
from main import app, CIVICPULSE_API_KEY, CLIENT_INGEST_TOKEN, incidents_db, INCIDENTS_FILE, engine

class TestTrustworthyAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.auth_headers = {"X-API-Key": CIVICPULSE_API_KEY}
        self.client_headers = (
            {"X-Client-Token": CLIENT_INGEST_TOKEN}
            if CLIENT_INGEST_TOKEN
            else self.auth_headers
        )

    def test_health(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "online")
        self.assertTrue(data["human_in_the_loop"])
        self.assertEqual(data["persistence"], "JSON Files")

    def test_protected_routes_require_authentication(self):
        # 1. /incidents/pending without key returns 401
        res = self.client.get("/incidents/pending")
        self.assertEqual(res.status_code, 401)

        # With admin key succeeds
        res_auth = self.client.get("/incidents/pending", headers=self.auth_headers)
        self.assertEqual(res_auth.status_code, 200)

        # 2. /audit-log without key returns 401
        res_audit = self.client.get("/audit-log")
        self.assertEqual(res_audit.status_code, 401)

        # With admin key succeeds
        res_audit_auth = self.client.get("/audit-log", headers=self.auth_headers)
        self.assertEqual(res_audit_auth.status_code, 200)

        # 3. /ingest without credentials returns 401
        res_ingest = self.client.post("/ingest", json={"sender_id": "+9199999", "text": "Hello"})
        self.assertEqual(res_ingest.status_code, 401)

        # With valid client token succeeds
        with patch.object(engine, "process_message", return_value={"action": "NOISE_DROP", "status": "NOISE"}):
            res_ingest_token = self.client.post(
                "/ingest", json={"sender_id": "+9199999", "text": "Hello"}, headers=self.client_headers
            )
        self.assertEqual(res_ingest_token.status_code, 200)

    def test_claim_lifecycle_create_resolve_audit(self):
        # 1. Create claim without key fails (401)
        new_claim = {
            "text": "Gas pipeline inspection in Block C confirmed clear by GAIL technician.",
            "category": "fire_safety",
            "source_links": ["https://gail.gov.in/notices/2026-11-22/block-c"],
            "verifier_identity": "GAIL Senior Safety Engineer",
            "verifier_status": "OFFICIALLY_VERIFIED"
        }
        res_unauth = self.client.post("/claims", json=new_claim)
        self.assertEqual(res_unauth.status_code, 401)

        # 2. Create claim with key succeeds
        res = self.client.post("/claims", json=new_claim, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        created = res.json()["claim"]
        claim_id = created["id"]
        self.assertEqual(
            self.client.post("/claims", json={**new_claim, "id": claim_id}, headers=self.auth_headers).status_code,
            409,
        )
        self.assertEqual(
            self.client.post(
                "/claims", json={**new_claim, "source_links": ["javascript:alert(1)"]},
                headers=self.auth_headers
            ).status_code,
            422,
        )
        self.assertEqual(created["status"], "ACTIVE")
        self.assertIsNone(created["resolved_at"])

        # 3. Resolve claim
        resolve_res = self.client.patch(f"/claims/{claim_id}/resolve", headers=self.auth_headers)
        self.assertEqual(resolve_res.status_code, 200)
        resolved_claim = resolve_res.json()["claim"]
        self.assertEqual(resolved_claim["status"], "RESOLVED")
        self.assertIsNotNone(resolved_claim["resolved_at"])

        # 4. Verify claim is excluded from active matching
        active_only = self.client.get("/claims?include_resolved=false").json()
        self.assertNotIn(claim_id, [c["id"] for c in active_only])

        # 5. Verify claim remains in history
        all_history = self.client.get("/claims?include_resolved=true").json()
        self.assertIn(claim_id, [c["id"] for c in all_history])

        # 6. Check audit log (with auth)
        audit_res = self.client.get("/audit-log", headers=self.auth_headers)
        self.assertEqual(audit_res.status_code, 200)
        logs = audit_res.json()
        self.assertTrue(any(l["action"] == "CLAIM_RESOLVED" and l["target_id"] == claim_id for l in logs))

    def test_separate_urgency_routing_unverified_to_review(self):
        # Brand new urgent need not matching any claim in the ledger
        urgent_payload = {
            "sender_id": "+919811199888",
            "text": "Emergency: Resident in D-203 having severe chest pain, need emergency first aid volunteer right now!",
            "latitude": 28.4595,
            "longitude": 77.0266
        }
        urgent_result = {
            "action": "NEEDS_REVIEW",
            "status": "UNVERIFIED_URGENT_PENDING",
            "urgency_level": "P1",
            "required_capability": "first_aid",
            "matched_claim": None,
            "entailment_score": 0.0,
            "dispatched_helpers": [],
            "dispatch_allowed": True,
        }
        with patch.object(engine, "process_message", return_value=urgent_result):
            res = self.client.post("/ingest", json=urgent_payload, headers=self.client_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        result = data["result"]

        # MUST be routed to NEEDS_REVIEW due to urgency, but flagged UNVERIFIED_URGENT_PENDING
        self.assertEqual(result["action"], "NEEDS_REVIEW")
        self.assertEqual(result["status"], "UNVERIFIED_URGENT_PENDING")
        self.assertEqual(result["urgency_level"], "P1")
        self.assertEqual(len(result["dispatched_helpers"]), 0) # Zero automatic dispatch!

        incident_id = result["incident_id"]

        # Human moderator approves the urgent call
        approve_res = self.client.post(
            f"/incidents/{incident_id}/approve",
            json={"moderator_notes": "Security guard verified resident is in distress, first aid dispatched."},
            headers=self.auth_headers
        )
        self.assertEqual(approve_res.status_code, 200)
        approved_data = approve_res.json()
        self.assertTrue(approved_data["incident"]["human_approved"])
        self.assertGreater(len(approved_data["incident"]["dispatched_helpers"]), 0)
        duplicate_approval = self.client.post(
            f"/incidents/{incident_id}/approve",
            json={"moderator_notes": "Duplicate approval must not dispatch twice."},
            headers=self.auth_headers
        )
        self.assertEqual(duplicate_approval.status_code, 409)

    def test_isolated_regression_suite_dry_run(self):
        # Snapshot current incident keys before test
        initial_incident_count = len(incidents_db)

        # 1. Test A: Exploded Rumour
        self.assertEqual(
            self.client.post("/api/test-regression", json={"scenario": "exploded"}).status_code,
            401,
        )
        deterministic_results = [
            {"action": "NEEDS_REVIEW", "status": "CONFLICTING_CLAIM_REVIEW", "contradiction_score": 0.95, "dispatch_allowed": False},
            {"action": "NEEDS_REVIEW", "status": "CORROBORATED", "entailment_score": 0.85, "dispatch_allowed": False},
        ]
        with patch.object(engine, "process_message", side_effect=deterministic_results) as process_mock:
            res_a = self.client.post(
                "/api/test-regression", json={"scenario": "exploded"}, headers=self.auth_headers
            )
            res_b = self.client.post(
                "/api/test-regression", json={"scenario": "operational"}, headers=self.auth_headers
            )
        self.assertEqual(process_mock.call_count, 2)
        self.assertIn("exploded", process_mock.call_args_list[0].args[0])
        self.assertIn("operational", process_mock.call_args_list[1].args[0])
        self.assertEqual(process_mock.call_args_list[0].args[1], main.REGRESSION_CLAIMS)
        self.assertEqual(process_mock.call_args_list[1].args[1], main.REGRESSION_CLAIMS)
        self.assertEqual(res_a.status_code, 200)
        data_a = res_a.json()
        self.assertTrue(data_a["dry_run"])
        self.assertEqual(data_a["result"]["action"], "NEEDS_REVIEW")
        self.assertEqual(data_a["result"]["status"], "CONFLICTING_CLAIM_REVIEW")
        self.assertFalse(data_a["result"]["dispatch_allowed"])

        # 2. Test B: Operational Corroboration
        self.assertEqual(res_b.status_code, 200)
        data_b = res_b.json()
        self.assertTrue(data_b["dry_run"])
        self.assertEqual(data_b["result"]["action"], "NEEDS_REVIEW")
        self.assertEqual(data_b["result"]["status"], "CORROBORATED")
        self.assertFalse(data_b["result"]["dispatch_allowed"])
        custom = self.client.post(
            "/api/test-regression",
            json={"scenario": "exploded", "custom_text": "unbounded custom input"},
            headers=self.auth_headers,
        )
        self.assertEqual(custom.status_code, 422)

        # 3. CRITICAL: Verify NO incident was saved to DB or incidents.json!
        self.assertEqual(len(incidents_db), initial_incident_count)
        if os.path.exists(INCIDENTS_FILE):
            with open(INCIDENTS_FILE, "r", encoding="utf-8") as f:
                saved_incidents = json.load(f)
            self.assertEqual(len(saved_incidents), initial_incident_count)

    def test_calibrated_fact_check_confidence_and_citations(self):
        # Stub the model response: tests must not send claim text to a provider.
        model_result = {
            "verdict": "FABRICATED_HOAX",
            "truth_score": 0.02,
            "falsehood_score": 0.98,
            "confidence": 0.99,
            "uncertainty_state": False,
            "summary": "This is a test response.",
            "explanation": "The model supplied test references.",
            "sources": [
                {"title": "Bad scheme", "url": "javascript:alert(1)", "type": "debunk_article"},
                {"title": "Generic homepage", "url": "https://example.org/", "type": "official_statement"},
                {"title": "Specific test page", "url": "https://example.org/fact-check/test", "type": "debunk_article"},
            ],
            "actionable_advice": "Check primary sources.",
        }
        fake_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(model_result)))]
        )
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **kwargs: fake_response)
            )
        )
        with patch.object(engine, "groq_client", fake_client):
            res = self.client.post(
                "/api/fact-check",
                json={"text": "Test claim with enough characters.", "context": "unit_test"},
            )

        self.assertEqual(res.status_code, 200)
        analysis = res.json()["analysis"]
        self.assertEqual(analysis["verdict"], "FABRICATED_HOAX")
        self.assertTrue(analysis["uncertainty_state"])
        self.assertFalse(analysis["sources_verified"])
        self.assertEqual(analysis["evidence_status"], "MODEL_REFERENCES_NOT_LIVE_VERIFIED")
        self.assertLessEqual(analysis["confidence"], 0.65)
        self.assertEqual(analysis["truth_score"], 0.5)
        self.assertEqual(len(analysis["sources"]), 1)
        self.assertIn("not been fetched", analysis["explanation"])

    def test_cors_does_not_reflect_arbitrary_extension_origins(self):
        res = self.client.options(
            "/api/fact-check",
            headers={
                "Origin": "chrome-extension://attacker-controlled-origin",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertNotEqual(
            res.headers.get("access-control-allow-origin"),
            "chrome-extension://attacker-controlled-origin",
        )

if __name__ == "__main__":
    unittest.main()
