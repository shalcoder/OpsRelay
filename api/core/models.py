from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, List, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ModelMixin:
    """Base mixin providing serialization helper for domain dataclasses."""
    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class Plant(ModelMixin):
    id: str
    name: str
    location: str


@dataclass
class User(ModelMixin):
    id: str
    name: str
    role: str  # "SUPERVISOR", "PLANT_MANAGER", "MAINTENANCE_ENGINEER"
    plantId: str = "PLANT-001"


@dataclass
class Prediction(ModelMixin):
    delayProbability: float
    failureProbability: float
    anomalyScore: float
    modelVersion: str = "sagemaker-v2.4"


@dataclass
class Evidence(ModelMixin):
    id: str
    source: str
    eventId: Optional[str] = None
    confidence: float = 1.0
    description: str = ""


@dataclass
class RiskAssessment(ModelMixin):
    id: str
    orderId: str
    riskScore: float
    severity: str  # "HEALTHY", "WATCH", "HIGH", "CRITICAL"
    factors: List[str] = field(default_factory=list)
    prediction: Optional[Prediction] = None
    evidence: List[Evidence] = field(default_factory=list)
    assessedAt: str = field(default_factory=now_iso)


@dataclass
class Recommendation(ModelMixin):
    id: str
    orderId: str
    actionType: str  # "REASSIGN_MACHINE", "ESCALATE_MAINTENANCE", "SPLIT_BATCH"
    rationale: str
    confidence: float
    status: str = "OPEN"  # "OPEN", "EXECUTED", "REJECTED"
    target: Optional[str] = None
    evidence: List[str] = field(default_factory=list)
    createdAt: str = field(default_factory=now_iso)


@dataclass
class Action(ModelMixin):
    id: str
    orderId: str
    recommendationId: str
    type: str
    status: str = "APPROVED"  # "APPROVED", "COMPLETED", "REJECTED"
    approvedBy: str = "SUPERVISOR-DIR-01"
    target: Optional[str] = None
    approvedAt: str = field(default_factory=now_iso)
    executedAt: Optional[str] = None


@dataclass
class AgentSession(ModelMixin):
    id: str
    orderId: Optional[str]
    question: str
    response: str
    userId: str = "USER-SUP-01"
    timestamp: str = field(default_factory=now_iso)


@dataclass
class Machine(ModelMixin):
    id: str
    name: str
    type: str  # "CNC Mill", "5-Axis Center", "Lathe"
    status: str = "AVAILABLE"  # "AVAILABLE", "RUNNING", "DEGRADED", "STOPPED", "DIAGNOSING", "MAINTENANCE"
    capacityPerHour: float = 25.0
    capabilities: List[str] = field(default_factory=lambda: ["MACHINING"])
    currentOrderId: Optional[str] = None
    lastEventAt: str = field(default_factory=now_iso)

    def is_available(self) -> bool:
        return self.status in {"AVAILABLE", "IDLE"}


@dataclass
class FactoryEvent(ModelMixin):
    id: str
    orderId: Optional[str]
    machineId: Optional[str]
    type: str  # "MACHINE_STOP", "MACHINE_DEGRADED", "QUALITY_REWORK", "MATERIAL_DELAY", etc.
    timestamp: str = field(default_factory=now_iso)
    source: str = "operator-edge-terminal"
    plantId: str = "PLANT-001"
    durationMinutes: float = 0.0
    delayHours: float = 0.0
    reworkUnits: int = 0
    description: str = ""


@dataclass
class ProductionOrder(ModelMixin):
    id: str
    customer: str
    product: str
    process: str  # "MACHINING", "MILLING", "DRILLING", "GRINDING"
    quantity: int
    completedQuantity: int = 0
    dueDate: str = field(default_factory=now_iso)
    assignedMachineId: Optional[str] = None
    status: str = "CREATED"  # "CREATED", "IN_PROGRESS", "AT_RISK", "INVESTIGATING", "RECOVERY_PROPOSED", "RECOVERY_PENDING", "RECOVERY_EXECUTING", "RECOVERY_VERIFIED", "COMPLETED", "DELAYED"
    createdAt: str = field(default_factory=now_iso)
    updatedAt: str = field(default_factory=now_iso)

    @property
    def progress_percent(self) -> float:
        if not self.quantity:
            return 0.0
        return min(100.0, round((self.completedQuantity / self.quantity) * 100.0, 2))
