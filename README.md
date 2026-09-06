# Luxury Authenticity — GenLayer

AI-verified luxury-goods authenticity screening with reusable on-chain records.
The chain cannot know whether a handbag, watch, or piece of jewelry is genuine,
so each check queries authoritative authentication sources and validators must
agree on the verdict before it is recorded. Records are reusable by any resale
platform or buyer.

## Lifecycle

```
submit_item(brand, model, serial, category)   # PENDING
process_item(id)      # queries authoritative sources + AI consensus -> COMPLETED, caches record
get_item(id)          # full check record
get_record(serial)    # reusable record (serial key, case-insensitive)
```

## Authoritative sources & retrieval evidence

Every check queries four authoritative authentication / resale sources built from
the serial number — **Entrupy** AI authentication, **Rebag** authenticity records,
**Vestiaire Collective** resale listings, and **eBay** listings — via
`gl.nondet.web.render`. Each source's URL, retrieval success, and a content excerpt
are preserved in the verdict and reusable record, so the evidence behind an
authenticity claim is auditable on-chain (see `sources[]`). Serials are validated
on-chain (4-40 characters, valid charset, normalized uppercase).

## Explicit inconclusive results

A verdict is never silently "authentic": the AI must return an explicit `status`
of `AUTHENTIC`, `COUNTERFEIT`, `SUSPICIOUS`, or `INCONCLUSIVE`. A source only
counts as `retrieved=True` when its response body actually references this
serial, so a generic landing/error page never counts as serial-specific
evidence. When no
authoritative source yields usable content, the check returns `INCONCLUSIVE` —
stored, surfaced, and counted separately in stats — rather than guessing a false
"authentic".

## Consensus binding

`gl.nondet.web.render` gathers the live source content and
`gl.eq_principle.prompt_comparative` binds the decision outputs — `status`
(AUTHENTIC/COUNTERFEIT/SUSPICIOUS/INCONCLUSIVE), `confidence` (0-100, validators
must agree within 10 points), `matched_records` (order-insensitive), and
`sources` (url + retrieved pairs, order-insensitive) so validators agree on
which authoritative sources were actually retrieved for this serial. `reasoning`
and excerpt wording may differ. Every verdict is normalized before storage.

## Hard source requirement

If no authoritative source was successfully retrieved for this serial, the
verdict is forced to `INCONCLUSIVE` in contract logic regardless of what the LLM
returned. An `AUTHENTIC` verdict must rest on serial-specific evidence, not on
generic page responses or empty results.

## Physical item evidence binding

Every `submit_item` call requires an `evidence_url` — a submitter-provided URL
(photo listing, marketplace listing, or certificate scan) that ties the serial to
a real physical item. Validators fetch this URL during consensus and verify the
response body references the serial. If the evidence is not retrieved or does not
contain the serial, the verdict is forced to `INCONCLUSIVE` — the serial is not
considered tied to a physical item. The record stores both `evidence_url` and
`evidence_retrieved` so it is bound to authenticated item evidence.

## Record ownership & collision guard

The reusable record is keyed by the normalized serial and stores full identity
(brand, model, category), the requester, and the originating check. A settled
record (`AUTHENTIC`/`COUNTERFEIT`/`SUSPICIOUS`) can only be replaced by its
original requester; an unrelated caller or a same-serial collision with a
different brand is rejected rather than silently overwriting the record. An
`INCONCLUSIVE` record may be improved by anyone (retry with better sources).

## Trust problem

Off-chain claims ("100% authentic, never used") are unverifiable on-chain. This
contract replaces trust with an AI-consensus authenticity verdict anchored to
authoritative live sources, recorded once and reused via `get_record`, so any
resale platform or buyer can gate on the outcome.

## Tests

```bash
pip install -r requirements.txt
python -m pytest tests/direct/ -v
```

Direct-mode tests (in-memory VM, no network/consensus) cover submit -> process ->
verdict, serial validation, authoritative-source querying, preserved retrieval
details, explicit INCONCLUSIVE handling, normalization (status enum + confidence
clamp), reusable caching, ownership/collision guards, state guards, and stats.

## Live

- Contract: `0xDee8F8624A7d54490BAb0c0dB262E0846152492B`
- Explorer: https://explorer-bradbury.genlayer.com/address/0xDee8F8624A7d54490BAb0c0dB262E0846152492B
- Deploy tx: `0x1cdc2759dbd23c1c428a302a3e08a58f8ee8876d74c748dbdacf94003293e5c6`
- Frontend: https://qlxjcj.github.io/genlayer-luxury-authenticity/
