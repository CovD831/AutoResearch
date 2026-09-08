# Acceptance and failure matrix

| Case | Expected result |
|---|---|
| bounded query succeeds | completed receipt, typed papers and candidates |
| network disabled/no seeds | unknown receipt and diagnostic; no invented paper |
| exact replay | replayed receipt, no second connector call |
| conflicting replay | `ValueError`, no mutation |
| invalid query/limit | `ValueError` before connector invocation |
| crash/pending reservation | explicit unknown outcome; no automatic duplicate retry |

Definition of done: adapter tests pass, ruff passes, the legacy facade remains
constructible, and review findings are consumed in the package ledger.
