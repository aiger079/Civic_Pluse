import atexit
import json
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from starlette.requests import Request

TEST_DATA_DIR = tempfile.mkdtemp(prefix="civicpulse-core-tests-")
os.environ["CIVICPULSE_DATA_DIR"] = TEST_DATA_DIR
atexit.register(shutil.rmtree, TEST_DATA_DIR, ignore_errors=True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main
from filter_engine import _bounded_score, _clean_suggested_sources


class TestOfflineCore(unittest.TestCase):
    def test_test_storage_is_isolated(self):
        self.assertEqual(main.DATA_DIR, os.path.abspath(TEST_DATA_DIR))
        self.assertNotEqual(main.DATA_DIR, os.path.join(main.BASE_DIR, "data"))

    def test_model_output_is_bounded_and_unsafe_sources_are_removed(self):
        model_result = {
            "verdict": "FABRICATED_HOAX",
            "truth_score": 0.02,
            "falsehood_score": 0.98,
            "confidence": 0.99,
            "summary": "Test claim",
            "explanation": "Preliminary result",
            "sources": [
                {"title": "Unsafe scheme", "url": "javascript:alert(1)", "type": "debunk_article"},
                {"title": "Generic root", "url": "https://example.org/", "type": "official_statement"},
                {"title": "Specific page", "url": "https://example.org/check/1", "type": "debunk_article"},
            ],
            "actionable_advice": "Check primary sources.",
        }
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(
                content=json.dumps(model_result),
                executed_tools=[{
                    "type": "browser_search",
                    "browser_results": [{
                        "title": "Specific page",
                        "url": "https://example.org/check/1",
                        "content": "A retrieved passage about the test claim.",
                    }],
                }],
            ))]
        )
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: response))
        )

        with patch.object(main.engine, "groq_client", fake_client):
            result = main.engine.fact_check_text("A test statement.")

        self.assertEqual(result["confidence"], 0.65)
        self.assertTrue(result["uncertainty_state"])
        self.assertFalse(result["sources_verified"])
        self.assertTrue(result["search_performed"])
        self.assertEqual(result["evidence_status"], "LIVE_SEARCH_RESULTS_UNVERIFIED")
        self.assertEqual(result["truth_score"], 0.5)
        self.assertEqual(len(result["sources"]), 1)
        self.assertEqual(result["sources"][0]["url"], "https://example.org/check/1")
        self.assertLessEqual(_bounded_score(float("inf")), 1.0)
        self.assertEqual(len(_clean_suggested_sources([{"title": "bad", "url": "javascript:alert(1)"}])), 0)

    def test_unconfirmed_claims_cannot_drive_nli_routing(self):
        claims = [
            {"id": "unconfirmed", "text": "Unverified assertion", "status": "ACTIVE", "verifier_status": "UNCONFIRMED"},
            {"id": "one-witness", "text": "One person saw it", "status": "ACTIVE", "verifier_status": "COMMUNITY_WITNESSED", "witness_count": 1},
            {"id": "confirmed", "text": "Admin reviewed source", "status": "ACTIVE", "verifier_status": "OFFICIALLY_VERIFIED"},
            {"id": "community", "text": "Two independent witnesses", "status": "ACTIVE", "verifier_status": "COMMUNITY_WITNESSED", "witness_count": 2},
        ]
        nli_result = {"is_uncertain": False, "entailment": 0.85, "contradiction": 0.05}
        with patch.object(main.engine, "check_toxicity", return_value=0.0), \
             patch.object(main.engine, "detect_urgency", return_value={"is_urgent": False, "urgency_level": "NONE"}), \
             patch.object(main.engine, "check_nli", return_value=nli_result) as nli_mock:
            routed = main.engine.process_message("A non-urgent update", claims)

        self.assertEqual(nli_mock.call_count, 2)
        matched_texts = [call.kwargs["premise"] for call in nli_mock.call_args_list]
        self.assertEqual(matched_texts, ["Admin reviewed source", "Two independent witnesses"])
        self.assertEqual(routed["action"], "NEEDS_REVIEW")
        self.assertFalse(routed["dispatch_allowed"])

    def test_contradictions_are_reviewed_not_suppressed_or_dispatched(self):
        claim = {
            "id": "confirmed",
            "text": "Transformer at Gate 1 is operational.",
            "status": "ACTIVE",
            "verifier_status": "OFFICIALLY_VERIFIED",
        }
        contradictory_nli = {"is_uncertain": False, "entailment": 0.02, "contradiction": 0.95}
        with patch.object(main.engine, "check_toxicity", return_value=0.0), \
             patch.object(main.engine, "detect_urgency", return_value={"is_urgent": False, "urgency_level": "NONE"}), \
             patch.object(main.engine, "check_nli", return_value=contradictory_nli):
            result = main.engine.process_message("Transformer failed", [claim])

        self.assertEqual(result["action"], "NEEDS_REVIEW")
        self.assertEqual(result["status"], "CONFLICTING_CLAIM_REVIEW")
        self.assertTrue(result["requires_human_approval"])
        self.assertFalse(result["dispatch_allowed"])

    def test_urgent_high_toxicity_message_still_reaches_human_review(self):
        urgency = {
            "is_urgent": True,
            "urgency_level": "P1",
            "required_capability": "first_aid",
        }
        with patch.object(main.engine, "check_toxicity", return_value=0.98), \
             patch.object(main.engine, "detect_urgency", return_value=urgency), \
             patch.object(main.engine, "check_nli", return_value={
                 "is_uncertain": False, "entailment": 0.0, "contradiction": 0.0, "neutral": 1.0,
             }):
            result = main.engine.process_message("Urgent request containing abusive language", [])

        self.assertEqual(result["action"], "NEEDS_REVIEW")
        self.assertEqual(result["status"], "UNVERIFIED_URGENT_PENDING")
        self.assertTrue(result["dispatch_allowed"])

    def test_urgent_message_with_unknown_capability_cannot_dispatch(self):
        urgency = {
            "is_urgent": True,
            "urgency_level": "P1",
            "required_capability": "arbitrary_capability",
        }
        with patch.object(main.engine, "check_toxicity", return_value=0.0), \
             patch.object(main.engine, "detect_urgency", return_value=urgency):
            result = main.engine.process_message("Urgent report", [])

        self.assertEqual(result["action"], "NEEDS_REVIEW")
        self.assertFalse(result["dispatch_allowed"])

    def test_dispatch_eligibility_fails_closed_for_nonurgent_or_unknown_capability(self):
        self.assertFalse(main.incident_dispatch_is_eligible({
            "dispatch_allowed": True,
            "urgency_level": "NONE",
            "required_capability": "first_aid",
        }))
        self.assertFalse(main.incident_dispatch_is_eligible({
            "dispatch_allowed": True,
            "urgency_level": "P1",
            "required_capability": "arbitrary_capability",
        }))
        self.assertFalse(main.incident_dispatch_is_eligible({
            "urgency_level": "P1",
            "required_capability": "first_aid",
        }))
        self.assertTrue(main.incident_dispatch_is_eligible({
            "dispatch_allowed": True,
            "urgency_level": "P1",
            "required_capability": "first_aid",
        }))

    def test_regression_endpoint_uses_only_fixed_dry_run_messages(self):
        before = dict(main.incidents_db)
        fake_result = {"action": "NEEDS_REVIEW", "status": "CORROBORATED", "dispatch_allowed": False}
        with patch.object(main.engine, "process_message", return_value=fake_result) as process_mock:
            response = main.run_regression_dry_run(main.RegressionTestRequest(scenario="operational"))

        self.assertTrue(response["dry_run"])
        self.assertIsNone(response["result"]["incident_id"])
        self.assertEqual(response["result"]["dispatched_helpers"], [])
        self.assertIn("operational", process_mock.call_args.args[0])
        self.assertEqual(process_mock.call_args.args[1], main.REGRESSION_CLAIMS)
        self.assertEqual(main.incidents_db, before)
        self.assertFalse(os.path.exists(main.INCIDENTS_FILE))

    def test_regression_request_rejects_custom_text(self):
        with self.assertRaises(Exception):
            main.RegressionTestRequest.model_validate({"scenario": "exploded", "custom_text": "arbitrary"})

    def test_new_claims_default_to_unconfirmed(self):
        claim = main.ClaimCreateSchema(
            text="A claim with no supplied verification status.",
            category="general",
            source_links=["https://example.org/notice/1"],
            verifier_identity="Test Admin",
        )
        self.assertEqual(claim.verifier_status, "UNCONFIRMED")

    def test_fact_check_telemetry_does_not_change_ingest_totals(self):
        before_messages = main.telemetry["total_messages"]
        before_fact_checks = main.telemetry["fact_checks"]
        result = {
            "verdict": "INSUFFICIENT_EVIDENCE",
            "falsehood_score": 0.5,
            "sources": [],
        }
        with patch.object(main.engine, "fact_check_text", return_value=result):
            scope = {
                "type": "http",
                "method": "POST",
                "path": "/api/fact-check",
                "scheme": "http",
                "headers": [],
                "query_string": b"",
                "server": ("testserver", 80),
                "client": ("test-client", 12345),
                "root_path": "",
            }
            main.fact_check(main.FactCheckRequest(text="A long enough test claim."), Request(scope))

        self.assertEqual(main.telemetry["total_messages"], before_messages)
        self.assertEqual(main.telemetry["fact_checks"], before_fact_checks + 1)

    def test_fact_check_quota_expires_after_rolling_window(self):
        ip = "rate-limit-test-client"
        for _ in range(main.FACT_CHECK_RATE_LIMIT):
            self.assertTrue(main.consume_fact_check_quota(ip, now=1000.0))
        self.assertFalse(main.consume_fact_check_quota(ip, now=1000.0))
        self.assertTrue(main.consume_fact_check_quota(ip, now=1061.0))

    def test_cors_uses_explicit_origins_without_credentials_or_regex(self):
        cors = next(item for item in main.app.user_middleware if item.cls.__name__ == "CORSMiddleware")
        self.assertIn("http://localhost:8000", cors.kwargs["allow_origins"])
        self.assertFalse(cors.kwargs["allow_credentials"])
        self.assertNotIn("allow_origin_regex", cors.kwargs)

    def test_atomic_json_write_replaces_with_complete_document(self):
        target = os.path.join(TEST_DATA_DIR, "atomic-test.json")
        main.save_json_atomically(target, {"state": "complete"})
        with open(target, "r", encoding="utf-8") as stream:
            self.assertEqual(json.load(stream), {"state": "complete"})
        self.assertEqual([name for name in os.listdir(TEST_DATA_DIR) if name.endswith(".tmp")], [])


if __name__ == "__main__":
    unittest.main()
