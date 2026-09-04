# Fixtures

The target fixture is `tests/test_capability_adapter.py::test_target_adapter_replays_without_second_connector_call` with a deterministic fake connector. The legacy fixture is the existing `PaperSearchService` path exercised by `tests/test_workflow.py` and the application tests.

The oracle is semantic: same request yields same paper payload and candidate
IDs; replay performs no connector call; changed request is rejected.
