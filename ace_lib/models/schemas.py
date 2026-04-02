"""Models and schemas for the ACE Orchestrator."""

from typing import Optional, List, Dict
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field


class TokenMode(str, Enum):
    """Token consumption mode."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskType(str, Enum):
    """Type of task being performed."""

    IMPLEMENT = "implement"
    REVIEW = "review"
    DEBUG = "debug"
    REFACTOR = "refactor"
    PLAN = "plan"


class Config(BaseModel):
    """Global configuration for ACE."""

    token_mode: TokenMode = TokenMode.LOW
    distributed_memory_url: Optional[str] = None
    distributed_memory_api_key: Optional[str] = None


class Decision(BaseModel):
    """Architectural Decision Record (ADR)."""

    id: str
    title: str
    status: str = "proposed"
    context: str
    decision: str
    consequences: str
    created_at: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    agent_id: Optional[str] = None


class Agent(BaseModel):
    """Agent definition in the registry."""

    id: str
    name: str
    role: str
    email: str
    created_by: str = "user"
    created_at: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    responsibilities: List[str] = Field(default_factory=list)
    memory_file: str
    status: str = "active"
    parent_id: Optional[str] = None
    sub_agent_ids: List[str] = Field(default_factory=list)
    allowed_paths: List[str] = Field(default_factory=list)  # RBAC: Paths the agent is allowed to modify
    forbidden_commands: List[str] = Field(default_factory=list)  # RBAC: Commands the agent is not allowed to run


class AgentsConfig(BaseModel):
    """Configuration for all agents."""

    version: str = "1"
    agents: List[Agent] = Field(default_factory=list)


class OwnershipModule(BaseModel):
    """Ownership information for a module or path."""

    agent_id: str
    owned_since: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d")
    )
    last_active: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d")
    )


class OwnershipConfig(BaseModel):
    """Configuration for module ownership."""

    version: str = "1"
    modules: Dict[str, OwnershipModule] = Field(default_factory=dict)
    unowned: List[str] = Field(default_factory=list)


class LivingSpec(BaseModel):
    """A living specification that evolves with the code."""

    id: str
    title: str
    intent: str
    constraints: List[str] = Field(default_factory=list)
    implementation: Optional[str] = None
    verification: Optional[str] = None
    status: str = "draft"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class CrossProjectLearning(BaseModel):
    """A learning exported for cross-project sharing."""

    source_project: str
    target_project: str
    strategy_id: str
    type: str  # str, mis, dec
    description: str
    helpful: int = 0
    harmful: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class TokenUsage(BaseModel):
    """Token usage tracking for a session."""

    agent_id: str
    session_id: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float = 0.0
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class ConsensusStatus(str, Enum):
    """Status of an MACP proposal."""

    PROPOSED = "proposed"
    DEBATING = "debating"
    CONSENSUS = "consensus"
    STALEMATE = "stalemate"
    ESCALATED = "escalated"


class MACPProposal(BaseModel):
    """A multi-agent consensus protocol proposal."""

    id: str
    title: str
    description: str
    proposer_id: str
    status: ConsensusStatus = ConsensusStatus.PROPOSED
    votes: Dict[str, str] = Field(default_factory=dict)  # agent_id -> vote
    turns_remaining: int = 3
    history: List[str] = Field(default_factory=list)
    consensus_summary: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class NotificationPriority(str, Enum):
    """Priority level for notifications."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Subscription(BaseModel):
    """An agent's subscription to a path."""

    agent_id: str
    path: str
    priority: NotificationPriority = NotificationPriority.MEDIUM
    notify_on_success: bool = True
    notify_on_failure: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class SubscriptionsConfig(BaseModel):
    """Configuration for all subscriptions."""

    version: str = "1"
    subscriptions: List[Subscription] = Field(default_factory=list)


class MailMessage(BaseModel):
    """A message sent between agents."""

    id: str
    from_agent: str = Field(..., alias="from")
    to_agent: str = Field(..., alias="to")
    subject: str
    body: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    status: str = "unread"

    model_config = {"populate_by_name": True}
