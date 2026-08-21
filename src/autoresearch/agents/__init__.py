from autoresearch.agents.orchestrator import OrchestratorAgent
from autoresearch.agents.paper_reader import PaperReaderAgent
from autoresearch.agents.paper_search import PaperSearchAgent
from autoresearch.agents.reviewer import ReviewerAgent
from autoresearch.agents.writer import WriterAgent
from autoresearch.contracts import AgentId

AGENT_TYPES = {
    AgentId.ORCHESTRATOR: OrchestratorAgent,
    AgentId.PAPER_SEARCH: PaperSearchAgent,
    AgentId.PAPER_READER: PaperReaderAgent,
    AgentId.WRITER: WriterAgent,
    AgentId.REVIEWER: ReviewerAgent,
}

assert set(AGENT_TYPES) == set(AgentId), "AutoResearch must expose exactly five agents"

__all__ = [
    "AGENT_TYPES",
    "OrchestratorAgent",
    "PaperSearchAgent",
    "PaperReaderAgent",
    "WriterAgent",
    "ReviewerAgent",
]
