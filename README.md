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
`gl.nondet.web.get`. Each source's URL, retrieval success, and a content excerpt
are preserved in the verdict and reusable record, so the evidence behind an
authenticity claim is auditable on-chain (see `sources[]`). Serials are validated
on-chain (4-40 characters, valid charset, normalized uppercase).

## Explicit inconclusive results

A verdict is never silently "authentic": the AI must return an explicit `status`
of `AUTHENTIC`, `COUNTERFEIT`, `SUSPICIOUS`, or `INCONCLUSIVE`. When no
authoritative source yields usable content, the check returns `INCONCLUSIVE` —
stored, surfaced, and counted separately in stats — rather than guessing a false
"authentic".

## Consensus binding

`gl.nondet.web.get` gathers the live source content and
`gl.eq_principle.prompt_comparative` binds the decision outputs — `status`
(AUTHENTIC/COUNTERFEIT/SUSPICIOUS/INCONCLUSIVE), `confidence` (0-100, validators
must agree within 10 points), and `matched_records` (order-insensitive) — so
validators cannot drift on the verdict. `reasoning` and `sources` may differ in
wording. Every verdict is normalized before storage.

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

- Contract: `0x69aD2dFBE1230E0B429D410bcb61Ecd549adBF0e`
- Explorer: https://explorer-bradbury.genlayer.com/address/0x69aD2dFBE1230E0B429D410bcb61Ecd549adBF0e
- Deploy tx: `0x1cdc2759dbd23c1c428a302a3e08a58f8ee8876d74c748dbdacf94003293e5c6`
- Frontend: https://qlxjcj.github.io/genlayer-luxury-authenticity/
