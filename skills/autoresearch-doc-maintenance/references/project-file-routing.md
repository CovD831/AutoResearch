# Project file routing

| Fact changed | File to update | Typical trigger |
|---|---|---|
| Task implementation and handoff | `.ai-team/tasks/<TASK-ID>.md`, task `PROGRESS.md`, `HANDOFF.md` | member PR submitted or corrected |
| Mainline integration queue | `.ai-team/TASK.md`, `docs/rearchitecture/TASK-PACKAGE-REGISTRY.md` | PR merged, rejected, or dependency unlocked |
| Overall objective/scope/current focus | `.project-to-act/PROJECT_OVERVIEW.md` | user changes product direction or phase focus |
| Milestone progress/blocker | `.project-to-act/PROJECT_PROGRESS.md` | phase/task milestone changes |
| Feature status | `.project-to-act/PROJECT_FEATURES.md` | a feature's acceptance evidence changes |
| Version/release status | `.project-to-act/PROJECT_VERSIONS.md` | release or compatibility decision changes |
| Acceptance/evidence/Gate | `.project-to-act/PROJECT_ACCEPTANCE.md` | a new Gate or acceptance result is verified |
| Architecture decision | `docs/rearchitecture/` + decision record | L1/L2/scope/owner changes |

Use the narrowest file set that records the new fact. Ordinary member progress should not touch all five Project-to-Act files.
