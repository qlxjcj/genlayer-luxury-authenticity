# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
import json
from dataclasses import dataclass
from genlayer import *


@allow_storage
@dataclass
class Item:
    item_id: str
    requester: str
    brand: str
    model: str
    serial: str
    category: str
    status: str
    verdict: str


class LuxuryAuthenticity(gl.Contract):
    items: TreeMap[str, str]
    records: TreeMap[str, str]
    item_count: u256

    STATUSES = ("AUTHENTIC", "COUNTERFEIT", "SUSPICIOUS", "INCONCLUSIVE")
    # Authoritative authentication / resale registries queried for every check.
    AUTHORITATIVE_SOURCES = (
        "https://www.entrupy.com/verify/",
        "https://www.rebag.com/authenticity/",
        "https://www.vestiairecollective.com/search/?q=",
        "https://www.ebay.com/sch/i.html?_nkw=",
    )

    def __init__(self):
        pass

    def _decode_body(self, content) -> str:
        body = getattr(content, "body", None)
        if body is None:
            return str(content)
        if isinstance(body, bytes):
            return body.decode("utf-8", errors="replace")
        return str(body)

    def _valid_serial(self, serial: str) -> str:
        serial = serial.strip().upper()
        if len(serial) < 4 or len(serial) > 40:
            raise gl.vm.UserError("Serial must be 4-40 characters")
        for ch in serial:
            if ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-":
                raise gl.vm.UserError("Serial contains invalid characters")
        return serial

    def _authoritative_urls(self, serial: str) -> list:
        return [base + serial for base in self.AUTHORITATIVE_SOURCES]

    def _authenticate(self, brand: str, model: str, serial: str, category: str) -> dict:
        def gather_and_authenticate() -> dict:
            sources = []
            texts = []
            for url in self._authoritative_urls(serial):
                try:
                    content = gl.nondet.web.get(url)
                    body = self._decode_body(content)[:1200]
                    texts.append(f"[{url}]\n{body}")
                    sources.append({"url": url, "retrieved": True, "excerpt": body[:400]})
                except Exception:
                    texts.append(f"[{url}] [FETCH_FAILED]")
                    sources.append({"url": url, "retrieved": False, "excerpt": ""})

            task = f"""
You are a luxury-goods authenticity screening engine. Base the verdict ONLY on the
authoritative sources below (Entrupy AI authentication, Rebag authenticity
records, Vestiaire Collective resale listings, eBay listings), which were queried
for this serial number. Cross-reference them for counterfeits, disputed items,
or indications that the piece is genuine.

If NO source was retrieved, or the retrieved sources do not cover this serial, you
MUST return status "INCONCLUSIVE" — never report an item as authentic without
evidence.

BRAND: {brand or "[none provided]"}
MODEL: {model or "[none provided]"}
SERIAL: {serial}
CATEGORY: {category or "[none provided]"}

SOURCES:
{chr(10).join(texts) if texts else "[none]"}

Evaluate: is the item authentic, counterfeit, or suspicious? Give a confidence
score (0-100) and name the specific records that matched. Be explicit and never
invent record identifiers.

Respond ONLY in this JSON format with exact fields:
{{
    "status": "AUTHENTIC" | "COUNTERFEIT" | "SUSPICIOUS" | "INCONCLUSIVE",
    "confidence": int,
    "matched_records": [str],
    "reasoning": str
}}

When status is "INCONCLUSIVE", set confidence=0, matched_records=[].
"""
            result = gl.nondet.exec_prompt(task, response_format="json")
            if isinstance(result, str):
                result = json.loads(result.replace("```json", "").replace("```", ""))
            if not isinstance(result, dict):
                raise gl.vm.UserError("[LLM_ERROR] LLM returned non-dict result")
            result["sources"] = sources
            return result

        principle = (
            "Two results are equivalent if status "
            "(AUTHENTIC/COUNTERFEIT/SUSPICIOUS/INCONCLUSIVE) matches exactly, "
            "confidence values differ by at most 10 points, and matched_records "
            "contains the same record identifiers (order-insensitive). reasoning "
            "and sources may differ in wording."
        )
        return gl.eq_principle.prompt_comparative(gather_and_authenticate, principle)

    def _normalize_verdict(self, v: dict) -> dict:
        status = str(v.get("status", "")).upper()
        if status not in self.STATUSES:
            status = "INCONCLUSIVE"
        try:
            confidence = int(v.get("confidence", 0))
        except Exception:
            confidence = 0
        if confidence < 0:
            confidence = 0
        if confidence > 100:
            confidence = 100
        matched = v.get("matched_records", [])
        if not isinstance(matched, list):
            matched = [str(matched)]
        matched = [str(x) for x in matched]

        if status == "INCONCLUSIVE":
            confidence = 0
            matched = []

        sources = v.get("sources", [])
        if not isinstance(sources, list):
            sources = []
        norm_sources = []
        for s in sources:
            if not isinstance(s, dict):
                continue
            norm_sources.append({
                "url": str(s.get("url", "")),
                "retrieved": bool(s.get("retrieved", False)),
                "excerpt": str(s.get("excerpt", ""))[:400],
            })

        return {
            "status": status,
            "confidence": confidence,
            "matched_records": matched,
            "sources": norm_sources,
            "reasoning": str(v.get("reasoning", "")),
        }

    @gl.public.write
    def submit_item(self, brand: str, model: str, serial: str, category: str):
        serial = self._valid_serial(serial)
        if not brand or not brand.strip():
            raise gl.vm.UserError("Brand is required")
        sender = gl.message.sender_address
        self.item_count += 1
        item_id = str(self.item_count)

        item = Item(
            item_id=item_id,
            requester=sender.as_hex,
            brand=brand.strip(),
            model=str(model or "").strip(),
            serial=serial,
            category=str(category or "").strip(),
            status="PENDING",
            verdict="",
        )
        self.items[item_id] = json.dumps(item.__dict__)

    @gl.public.write
    def process_item(self, item_id: str):
        item_id = str(item_id)
        item = json.loads(self.items.get(item_id, "{}"))
        if not item:
            raise gl.vm.UserError("Check not found")
        if item["status"] != "PENDING":
            raise gl.vm.UserError("Already processed")

        verdict = self._normalize_verdict(
            self._authenticate(item["brand"], item["model"], item["serial"], item["category"])
        )

        # Reusable record is keyed by normalized serial. Guard against an unrelated
        # caller (or a serial collision with a different brand) silently replacing
        # a settled record: only its original requester may update it, and anyone
        # may improve an INCONCLUSIVE one.
        key = item["serial"]
        existing = json.loads(self.records.get(key, "{}"))
        if existing:
            settled = existing.get("status") != "INCONCLUSIVE"
            same_owner = existing.get("requester") == item["requester"]
            if settled and not same_owner:
                raise gl.vm.UserError(
                    "Reusable record for this serial is already settled by another requester"
                )

        item["status"] = "COMPLETED"
        item["verdict"] = json.dumps(verdict, sort_keys=True)
        self.items[item_id] = json.dumps(item)

        record = dict(verdict)
        record["brand"] = item["brand"]
        record["model"] = item["model"]
        record["serial"] = item["serial"]
        record["category"] = item["category"]
        record["requester"] = item["requester"]
        record["from_check"] = item["item_id"]
        self.records[key] = json.dumps(record, sort_keys=True)

    @gl.public.view
    def get_item(self, item_id: str) -> str:
        return self.items.get(str(item_id), "{}")

    @gl.public.view
    def get_record(self, serial: str) -> str:
        return self.records.get(self._valid_serial(serial), "{}")

    @gl.public.view
    def get_item_count(self) -> int:
        return self.item_count

    @gl.public.view
    def get_stats(self) -> dict:
        authentic = 0
        counterfeit = 0
        suspicious = 0
        inconclusive = 0
        for v in self.items.values():
            r = json.loads(v)
            if r["status"] == "COMPLETED" and r["verdict"]:
                verdict = json.loads(r["verdict"])
                st = verdict.get("status", "INCONCLUSIVE")
                if st == "AUTHENTIC":
                    authentic += 1
                elif st == "COUNTERFEIT":
                    counterfeit += 1
                elif st == "SUSPICIOUS":
                    suspicious += 1
                else:
                    inconclusive += 1
        return {
            "total": len(self.items),
            "completed": authentic + counterfeit + suspicious + inconclusive,
            "authentic": authentic,
            "counterfeit": counterfeit,
            "suspicious": suspicious,
            "inconclusive": inconclusive,
            "records": len(self.records),
        }
