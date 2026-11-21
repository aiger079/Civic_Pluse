import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from filter_engine import DualGateEngine

def run_tests():
    print("=" * 65)
    print("CIVICPULSE DUAL-GATE AI ENGINE: SYNTHETIC REGRESSION SUITE")
    print("=" * 65)

    engine = DualGateEngine()

    # Synthetic fixtures; never load claims from the user's live ledger here.
    active_claims = [
        {
            "id": "claim_flood",
            "text": "Tower B basement is completely flooded with water due to rain.",
            "category": "utility_flood",
            "source_links": [],
            "verifier_status": "COMMUNITY_WITNESSED",
            "witness_count": 3
        },
        {
            "id": "claim_transformer",
            "text": "Transformer at Gate 1 is operational; power restored in Tower C.",
            "category": "electrical_grid",
            "source_links": [],
            "verifier_status": "OFFICIALLY_VERIFIED",
            "witness_count": 5
        }
    ]

    test_messages = [
        # Regression Case A: Direct contradiction of operational transformer
        {
            "name": "Regression Case A: 'Transformer exploded' vs Synthetic Operational Fixture",
            "text": "Main gate transformer exploded, entire complex will have blackout for next 3 days!",
            "expected_action": "NEEDS_REVIEW",
            "expected_status": "CONFLICTING_CLAIM_REVIEW"
        },
        # Regression Case B: Corroboration of operational transformer
        {
            "name": "Regression Case B: 'Transformer operational' vs Synthetic Operational Fixture",
            "text": "Transformer operational, lights are working fine at Gate 1 and Tower C.",
            "expected_action": "NEEDS_REVIEW",
            "expected_status": "CORROBORATED"
        },
        # Case C: Toxic Insult
        {
            "name": "Case C: Abusive Resident Message",
            "text": "Tum sab bewakoof ho, Lift main kyu kachra feka hai tum logo ne!",
            "expected_action": "SUPPRESS_TOXIC",
            "expected_status": "HUMILIATION_FLAGGED"
        },
        # Case D: Synthetic Flood with Human-in-the-Loop review requirement
        {
            "name": "Case D: Synthetic Basement Flood Emergency (Requires Review)",
            "text": "Block B parking area mein pani bhar gaya hai, basement flooded. Need drainage pump urgent!",
            "expected_action": "NEEDS_REVIEW",
            "expected_status": "CORROBORATED"
        },
        # Case E: Auditable Fact-Check with Sources & Confidence
        {
            "name": "Case E: Preliminary Model Assessment (NASA 5G Claim)",
            "text": "NASA satellite confirms 5G radiation is shutting down society water pumps.",
            "expected_action": "FACT_CHECK"
        }
    ]

    passed = 0
    total = len(test_messages)

    for i, test in enumerate(test_messages, 1):
        print(f"\n--- [{i}/{total}] Testing: {test['name']} ---")
        print(f"Input: \"{test['text']}\"")

        if test["expected_action"] == "FACT_CHECK":
            res = engine.fact_check_text(test["text"])
            print(f"Verdict: {res.get('verdict')}")
            print(f"Confidence: {res.get('confidence')} | Truth Score: {res.get('truth_score')}")
            print(f"Sources Cited: {len(res.get('sources', []))} source(s)")
            for s in res.get("sources", []):
                print(f"   - {s.get('title')}: {s.get('url')}")
            print(f"Uncertainty State: {res.get('uncertainty_state')}")

            # The app does not retrieve citations; it must disclose that and cap confidence.
            if (
                res.get("uncertainty_state") is True
                and res.get("sources_verified") is False
                and res.get("evidence_status") == "MODEL_REFERENCES_NOT_LIVE_VERIFIED"
                and float(res.get("confidence", 1.0)) <= 0.65
            ):
                print("PASSED: Unverified references and calibrated uncertainty are disclosed.")
                passed += 1
            else:
                print("Fact check failed assertion:", res)
        else:
            res = engine.process_message(test["text"], active_claims)
            print(f"Action: {res.get('action')} | Status: {res.get('status')}")
            print(f"   Toxicity: {res.get('toxicity_score')} | Entail: {res.get('entailment_score')} | Contradict: {res.get('contradiction_score')}")
            print(f"   Requires Human Approval: {res.get('requires_human_approval')}")
            
            matched = res.get("matched_claim")
            if matched:
                print(f"   Matched Evidence Claim: [{matched.get('id')}] (Status: {matched.get('verifier_status')})")
                print(f"      Sources: {matched.get('source_links')}")

            if res.get("action") == test["expected_action"] and res.get("status") == test["expected_status"]:
                print("PASSED: Action and status match expected thresholds.")
                passed += 1
            else:
                print(f"Mismatch: expected ({test['expected_action']}, {test['expected_status']}), got ({res.get('action')}, {res.get('status')})")

    print("\n" + "=" * 65)
    print(f"Test Results: {passed}/{total} Passed")
    print("=" * 65)

if __name__ == "__main__":
    run_tests()
