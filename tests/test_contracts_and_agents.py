from __future__ import annotations

import pytest
from pydantic import ValidationError

from autoresearch.agents import AGENT_TYPES
from autoresearch.contracts import AgentId, HandoffEnvelope, LifecycleState
from autoresearch.state_machine import StateMachine


def test_registry_contains_exactly_five_business_agents():
    assert set(AGENT_TYPES) == set(AgentId)
    assert len(AGENT_TYPES) == 5


def test_handoff_rejects_self_handoff_and_unbounded_context():
    base = {
        "project_id": "demo",
        "run_id": "run_1",
        "from_agent": AgentId.ORCHESTRATOR,
        "to_agent": AgentId.ORCHESTRATOR,
        "objective": "Do work",
        "expected_output": "Artifact IDs",
    }
    with pytest.raises(ValidationError):
        HandoffEnvelope.model_validate(base)

    base["to_agent"] = AgentId.PAPER_SEARCH
    base["bounded_context"] = "x" * 2001
    with pytest.raises(ValidationError):
        HandoffEnvelope.model_validate(base)


def test_state_machine_rejects_stage_skipping():
    with pytest.raises(ValueError):
        StateMachine().transition(
            LifecycleState.INTAKE,
            LifecycleState.DRAFT_WRITTEN,
        )
