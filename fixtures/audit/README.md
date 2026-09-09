# Audit Fixture Provenance

`citations.jsonl` is a synthetic, offline ground-truth fixture set. Each record
is intentionally labeled by `scenario_id`; resolver rows are local test facts and
are not claims about real scholarly records. The fixture covers presence,
absence, retraction, correction, locator match/mismatch, resolver outage, and an
unbound claim so the acceptance command can run without network access.
