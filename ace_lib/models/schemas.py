from typing import Optional, List, Dict
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field


class TokenMode(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskType(str, Enum):
    IMPLEMENT = "implement"
    REVIEW = "review"
    DEBUG = "debug"
    REFACTOR = "refactor"
    PLAN = "plan"


class Config(BaseModel):
    token_mode: TokenMode = TokenMode.LOW


class Decision(BaseModel):
    id: str
    title: str
    status: str = "proposed"
    context: str
    decision: str
    consequences: str
    created_at: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d")
    )
    agent_id: Optional[str] = None


class Agent(BaseModel):
    id: str
    name: str
    role: str
    email: str
    created_by: str = "user"
    created_at: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d")
    )
    responsibilities: List[str] = Field(default_factory=list)
    memory_file: str
    status: str = "active"


class AgentsConfig(BaseModel):
    version: str = "1"
    agents: List[Agent] = Field(default_factory=list)


class OwnershipModule(BaseModel):
    agent_id: str
    owned_since: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d")
    )
    last_active: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d")
    )


class OwnershipConfig(BaseModel):
    version: str = "1"
    modules: Dict[str, OwnershipModule] = Field(default_factory=dict)
    unowned: List[str] = Field(default_factory=list)


class LivingSpec(BaseModel):
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
    source_project: str
    target_project: str
    strategy_id: str
    type: str  # str, mis, dec
    description: str
    helpful: int = 0
    harmful: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class TokenUsage(BaseModel):
    agent_id: str
    session_id: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float = 0.0
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class Subscription(BaseModel):
    agent_id: str
    path: str
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class SubscriptionsConfig(BaseModel):
    version: str = "1"
    subscriptions: List[Subscription] = Field(default_factory=list)


class MailMessage(BaseModel):
    id: str
    from_agent: str = Field(..., alias="from")
    to_agent: str = Field(..., alias="to")
    subject: str
    body: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    status: str = "unread"

    model_config = {
        "populate_by_name": True
    }
