"""Direct-mode tests for Luxury Authenticity.

Covers the authentication lifecycle: submit -> process (AI consensus) ->
COMPLETED with a normalized, reusable verdict. Verifies authoritative-source
querying with preserved retrieval details, explicit INCONCLUSIVE results,
normalization (status enum + confidence clamp), reusable on-chain records,
ownership/collision guards, state guards, and stats.

No network, no consensus: deterministic and instant.
Run: python -m pytest tests/direct/ -v   (from the project root)
"""

import json
import pytest

from conftest import (
    SERIAL,
    VERDICT_AUTHENTIC,
    VERDICT_COUNTERFEIT,
    VERDICT_INCONCLUSIVE,
    VERDICT_MALFORMED,
    VERDICT_SUSPICIOUS,
    LLM_PATTERN,
)


def _check(c, cid):
    return json.loads(c.get_item(cid))


def _verdict(c, cid):
    return json.loads(_check(c, cid)["verdict"])


def _record(c, serial):
    return json.loads(c.get_record(serial)) if c.get_record(serial) != "{}" else None


# ---------- submit ----------

def test_submit_creates_pending_check(direct_vm, la):
    vm, c = la
    c.submit_item("Rolex", "Submariner", SERIAL, "watch")

    assert c.get_item_count() == 1
    r = _check(c, 1)
    assert r["status"] == "PENDING"
    assert r["serial"] == SERIAL.upper()
    assert r["brand"] == "Rolex"
    assert r["verdict"] == ""
    assert r["requester"]


def test_submit_normalizes_serial_case(direct_vm, la):
    vm, c = la
    c.submit_item("Rolex", "Submariner", "rolex00012345", "watch")
    assert _check(c, 1)["serial"] == SERIAL.upper()


def test_submit_rejects_short_serial(direct_vm, la):
    vm, c = la
    with pytest.raises(Exception) as ei:
        c.submit_item("Rolex", "Submariner", "RO", "watch")
    assert "4-40" in str(ei.value)


def test_submit_rejects_bad_serial_chars(direct_vm, la):
    vm, c = la
    with pytest.raises(Exception) as ei:
        c.submit_item("Rolex", "Submariner", "ROLEX_00012345", "watch")
    assert "invalid" in str(ei.value).lower()


def test_submit_rejects_missing_brand(direct_vm, la):
    vm, c = la
    with pytest.raises(Exception) as ei:
        c.submit_item("   ", "Submariner", SERIAL, "watch")
    assert "Brand" in str(ei.value)


# ---------- process: statuses ----------

def test_process_authentic(direct_vm, la):
    vm, c = la
    c.submit_item("Rolex", "Submariner", SERIAL, "watch")
    c.process_item(1)

    r = _check(c, 1)
    assert r["status"] == "COMPLETED"
    v = _verdict(c, 1)
    assert v["status"] == "AUTHENTIC"
    assert v["confidence"] == 95
    assert "ENTRUPY-CERT-2024-88" in v["matched_records"]


def test_process_counterfeit(direct_vm, la):
    vm, c = la
    vm.clear_mocks()
    vm.mock_llm(LLM_PATTERN, VERDICT_COUNTERFEIT)
    c.submit_item("Rolex", "Submariner", SERIAL, "watch")
    c.process_item(1)

    v = _verdict(c, 1)
    assert v["status"] == "COUNTERFEIT"
    assert "REBAG-FLAG-3301" in v["matched_records"]


def test_process_suspicious(direct_vm, la):
    vm, c = la
    vm.clear_mocks()
    vm.mock_llm(LLM_PATTERN, VERDICT_SUSPICIOUS)
    c.submit_item("Rolex", "Submariner", SERIAL, "watch")
    c.process_item(1)

    v = _verdict(c, 1)
    assert v["status"] == "SUSPICIOUS"
    assert v["confidence"] == 45


# ---------- authoritative sources + retrieval details ----------

def test_record_queries_authoritative_sources(direct_vm, la):
    vm, c = la
    c.submit_item("Rolex", "Submariner", SERIAL, "watch")
    c.process_item(1)

    rec = _record(c, SERIAL)
    urls = [s["url"] for s in rec["sources"]]
    assert any("entrupy.com" in u for u in urls)            # Entrupy AI authentication
    assert any("rebag.com" in u for u in urls)              # Rebag authenticity
    assert any("vestiairecollective.com" in u for u in urls)  # Vestiaire resale
    assert any("ebay.com" in u for u in urls)               # eBay listings
    assert len(urls) == 4
    assert SERIAL.upper() in urls[0]
    # no source mocked -> all retrieval attempts recorded as failed
    assert all(s["retrieved"] is False for s in rec["sources"])
    assert all(s["excerpt"] == "" for s in rec["sources"])


def test_record_preserves_retrieval_details(direct_vm, la):
    vm, c = la
    vm.mock_web(r".*rebag\.com.*", {
        "method": "GET", "status": 200,
        "body": "Entrupy certificate ENT-2024-88 confirms this serial is genuine.",
    })
    c.submit_item("Rolex", "Submariner", SERIAL, "watch")
    c.process_item(1)

    rec = _record(c, SERIAL)
    rebag = next(s for s in rec["sources"] if "rebag.com" in s["url"])
    assert rebag["retrieved"] is True
    assert "genuine" in rebag["excerpt"]
    others = [s for s in rec["sources"] if "rebag.com" not in s["url"]]
    assert all(s["retrieved"] is False for s in others)


# ---------- explicit inconclusive ----------

def test_inconclusive_explicit(direct_vm, la):
    vm, c = la
    vm.clear_mocks()
    vm.mock_llm(LLM_PATTERN, VERDICT_INCONCLUSIVE)
    c.submit_item("Rolex", "Submariner", SERIAL, "watch")
    c.process_item(1)

    v = _verdict(c, 1)
    assert v["status"] == "INCONCLUSIVE"
    assert v["confidence"] == 0
    assert v["matched_records"] == []
    assert _record(c, SERIAL)["status"] == "INCONCLUSIVE"


# ---------- verdict normalization ----------

def test_verdict_normalized(direct_vm, la):
    vm, c = la
    vm.clear_mocks()
    vm.mock_llm(LLM_PATTERN, VERDICT_MALFORMED)
    c.submit_item("Rolex", "Submariner", SERIAL, "watch")
    c.process_item(1)

    v = _verdict(c, 1)
    assert v["status"] == "INCONCLUSIVE"          # invalid enum coerced
    assert v["confidence"] == 0                   # 500 clamped + inconclusive zeroes it
    assert v["matched_records"] == []             # cleared for inconclusive


def test_confidence_clamped_upper(direct_vm, la):
    vm, c = la
    vm.clear_mocks()
    vm.mock_llm(LLM_PATTERN, json.dumps({
        "status": "AUTHENTIC", "confidence": 150, "matched_records": [], "reasoning": "x",
    }))
    c.submit_item("Rolex", "Submariner", SERIAL, "watch")
    c.process_item(1)
    assert _verdict(c, 1)["confidence"] == 100


# ---------- reusable on-chain record ----------

def test_record_cached_and_case_insensitive(direct_vm, la):
    vm, c = la
    c.submit_item("Rolex", "Submariner", SERIAL, "watch")
    c.process_item(1)

    rec = _record(c, SERIAL)
    assert rec["status"] == "AUTHENTIC"
    assert rec["serial"] == SERIAL.upper()
    assert rec["requester"]
    assert rec["from_check"] == "1"
    rec2 = _record(c, SERIAL.lower())
    assert rec2["status"] == "AUTHENTIC"


def test_get_record_unknown(direct_vm, la):
    vm, c = la
    assert c.get_record("HERMES00012345") == "{}"


# ---------- record ownership / collision guards ----------

def test_unrelated_caller_cannot_replace_record(direct_vm, la, direct_bob):
    vm, c = la
    c.submit_item("Rolex", "Submariner", SERIAL, "watch")
    c.process_item(1)
    owner = _record(c, SERIAL)["requester"]

    vm.sender = direct_bob
    c.submit_item("Rolex", "Submariner", SERIAL, "watch")
    with pytest.raises(Exception) as ei:
        c.process_item(2)
    assert "settled by another requester" in str(ei.value).lower()

    rec = _record(c, SERIAL)
    assert rec["requester"] == owner
    assert rec["from_check"] == "1"


def test_serial_collision_with_different_brand_rejected(direct_vm, la, direct_bob):
    vm, c = la
    c.submit_item("Rolex", "Submariner", SERIAL, "watch")
    c.process_item(1)

    # same serial, different brand, unrelated caller -> rejected, not overwritten
    vm.sender = direct_bob
    c.submit_item("Hermes", "Birkin", SERIAL, "bag")
    with pytest.raises(Exception) as ei:
        c.process_item(2)
    assert "settled" in str(ei.value).lower()
    assert _record(c, SERIAL)["brand"] == "Rolex"


def test_same_requester_can_refresh_record(direct_vm, la):
    vm, c = la
    c.submit_item("Rolex", "Submariner", SERIAL, "watch")
    c.process_item(1)

    c.submit_item("Rolex", "Submariner", SERIAL, "watch")
    c.process_item(2)
    assert _record(c, SERIAL)["from_check"] == "2"


def test_inconclusive_record_can_be_improved_by_anyone(direct_vm, la, direct_bob):
    vm, c = la
    vm.clear_mocks()
    vm.mock_llm(LLM_PATTERN, VERDICT_INCONCLUSIVE)
    c.submit_item("Rolex", "Submariner", SERIAL, "watch")
    c.process_item(1)
    assert _record(c, SERIAL)["status"] == "INCONCLUSIVE"

    vm.sender = direct_bob
    vm.clear_mocks()
    vm.mock_llm(LLM_PATTERN, VERDICT_COUNTERFEIT)
    c.submit_item("Rolex", "Submariner", SERIAL, "watch")
    c.process_item(2)
    rec = _record(c, SERIAL)
    assert rec["status"] == "COUNTERFEIT"
    assert rec["requester"] == direct_bob.as_hex


# ---------- state guards ----------

def test_process_twice_blocked(direct_vm, la):
    vm, c = la
    c.submit_item("Rolex", "Submariner", SERIAL, "watch")
    c.process_item(1)

    with pytest.raises(Exception) as ei:
        c.process_item(1)
    assert "processed" in str(ei.value).lower()


def test_process_not_found(direct_vm, la):
    vm, c = la
    with pytest.raises(Exception) as ei:
        c.process_item(99)
    assert "not found" in str(ei.value).lower()


# ---------- stats ----------

def test_stats_counts_statuses(direct_vm, la):
    vm, c = la
    c.submit_item("Rolex", "Submariner", SERIAL, "watch")
    c.process_item(1)

    vm.clear_mocks()
    vm.mock_llm(LLM_PATTERN, VERDICT_COUNTERFEIT)
    c.submit_item("Hermes", "Birkin", "HERMES00012345", "bag")
    c.process_item(2)

    vm.clear_mocks()
    vm.mock_llm(LLM_PATTERN, VERDICT_SUSPICIOUS)
    c.submit_item("Chanel", "Classic", "CHANEL00012345", "bag")
    c.process_item(3)

    vm.clear_mocks()
    vm.mock_llm(LLM_PATTERN, VERDICT_INCONCLUSIVE)
    c.submit_item("Gucci", "Marmont", "GUCCI00012345", "bag")
    c.process_item(4)

    s = c.get_stats()
    assert s["total"] == 4
    assert s["completed"] == 4
    assert s["authentic"] == 1
    assert s["counterfeit"] == 1
    assert s["suspicious"] == 1
    assert s["inconclusive"] == 1
    assert s["records"] == 4
