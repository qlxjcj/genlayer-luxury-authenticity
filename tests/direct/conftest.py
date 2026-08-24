"""Shared fixtures for Luxury Authenticity direct-mode tests.

Direct mode runs the real contract source in-process. The AI authentication
screening is mocked so tests are deterministic and instant, with no network or
consensus dependency.
"""

import json
import os
import pytest

CONTRACT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "luxury_authenticity.py",
)

SERIAL = "ROLEX00012345"

VERDICT_AUTHENTIC = json.dumps({
    "status": "AUTHENTIC",
    "confidence": 95,
    "matched_records": ["ENTRUPY-CERT-2024-88"],
    "reasoning": "Serial matches a certified genuine listing.",
})

VERDICT_COUNTERFEIT = json.dumps({
    "status": "COUNTERFEIT",
    "confidence": 90,
    "matched_records": ["REBAG-FLAG-3301"],
    "reasoning": "Serial appears on a counterfeit watchlist.",
})

VERDICT_SUSPICIOUS = json.dumps({
    "status": "SUSPICIOUS",
    "confidence": 45,
    "matched_records": ["VESTIAIRE-DISPUTE-12"],
    "reasoning": "Conflicting signals; item disputed on resale.",
})

VERDICT_INCONCLUSIVE = json.dumps({
    "status": "INCONCLUSIVE",
    "confidence": 0,
    "matched_records": [],
    "reasoning": "Authoritative sources could not be retrieved for this serial.",
})

# Missing / invalid fields to prove verdict normalization.
VERDICT_MALFORMED = json.dumps({
    "status": "definitely-real",
    "confidence": 500,
    "matched_records": "ENTRUPY-CERT-2024-88",
})

LLM_PATTERN = r".*luxury-goods authenticity screening engine.*"

# A successful authoritative source whose body references the serial, so
# verdicts have at least one serial-specific retrieved source.
SOURCE_OK = r".*rebag\.com.*"
SOURCE_BODY = "Entrupy certificate ENT-2024-88 confirms serial " + SERIAL + " is genuine."


def with_source(vm, body=SOURCE_BODY):
    vm.mock_web(SOURCE_OK, {"method": "GET", "status": 200, "body": body})


@pytest.fixture
def la(direct_vm, direct_deploy):
    vm = direct_vm
    vm.mock_llm(LLM_PATTERN, VERDICT_AUTHENTIC)
    with_source(vm)
    c = direct_deploy(CONTRACT)
    return vm, c
