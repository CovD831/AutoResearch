# B2 Evidence Adversarial

Status: `active`.

This task is the bounded adversarial follow-up to B1. It hardens only evidence
admission, evidence eligibility, benchmark readiness, and Evaluation section
validation. It does not add an agent, store, bus, scheduler, network adapter,
Audit module, or real pilot.

The implementation is based on the B1-integrated remote `main` at
`c1dbefc9edd3b53798c321cac06537a6faba5d3d` (`c1dbefc`). The B2 changes were
restored into a fresh working tree from this base and are ready for commit and
PR review; no B1 rebase is pending.

The task contract is split into:

- `TASK-PACKAGE.md`: boundary and acceptance contract;
- `L3.md`: implementation-level rules;
- `PROGRESS.md`: status and evidence ledger;
- `HANDOFF.md`: final integration handoff;
- `task-package.json`: machine-readable package metadata.
