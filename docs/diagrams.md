# OpsRelay Mermaid diagrams

The system is represented at business, logical, cloud, UML-style, ML, security, and resilience levels. Mermaid flowcharts are used where Mermaid does not provide a native UML notation.

## 1. End-to-End System Architecture

```mermaid
flowchart TB
  U1["Production Supervisor"] --> UI["OpsRelay Web Control Center"]
  U2["Plant Manager"] --> UI
  U3["Maintenance Engineer"] --> UI
  subgraph FACTORY["Factory Data"]
    I1["WhatsApp / Manual Updates"]
    I2["Excel / CSV Orders"]
    I3["Machine / IoT Signals"]
    I4["Maintenance Events"]
    I5["Quality / Rework"]
    I6["Production Events"]
  end
  I1 --> EDGE["Edge Gateway"]
  I2 --> EDGE
  I3 --> EDGE
  I4 --> EDGE
  I5 --> EDGE
  I6 --> EDGE
  EDGE --> API["API Gateway"]
  UI --> COG["Cognito"] --> API
  API --> ING["Ingestion Lambda"]
  ING --> S3["S3 Raw Events"]
  ING --> DDB["DynamoDB"]
  ING --> EB["EventBridge"] --> Q["SQS"] --> PROC["Processor Lambda"]
  DDB --> RISK["Deterministic Risk Engine"]
  PROC --> SM["SageMaker AI"] --> RISK
  DDB --> STR["Strands Agent"]
  RISK --> STR
  STR --> TOOLS["Operational Tools"] --> ACT["Action Service"]
  ACT --> APPROVE["Human Approval"]
  APPROVE --> DDB
  API --> UI
  ING --> CW["CloudWatch"]
  PROC --> CW
  SM --> CW
  STR --> CW
  ACT --> CW
```

## 2. Logical Architecture

```mermaid
flowchart LR
  A["Experience Layer"] --> B["API + Identity"] --> C["Event + Data"] --> D["Intelligence"] --> E["Decision"] --> F["Action"] --> G["Observability"]
  A1["Dashboard"] --> A
  A2["Risk Board"] --> A
  A3["Agent Console"] --> A
  B1["API Gateway"] --> B
  B2["Cognito"] --> B
  C1["S3"] --> C
  C2["DynamoDB"] --> C
  C3["EventBridge"] --> C
  C4["SQS"] --> C
  D1["SageMaker AI"] --> D
  D2["Delay / Failure / Anomaly"] --> D
  E1["Risk Engine"] --> E
  E2["Evidence Retrieval"] --> E
  E3["Strands Agent"] --> E
  F1["Approval"] --> F
  F2["Execution"] --> F
  G1["CloudWatch"] --> G
```

## 3. Use Cases

```mermaid
flowchart LR
  SUP["Production Supervisor"]
  MGR["Plant Manager"]
  ENG["Maintenance Engineer"]
  subgraph O["OpsRelay"]
    U1(("View Risk"))
    U2(("Ingest Signal"))
    U3(("Investigate Order"))
    U4(("View Evidence"))
    U5(("Ask Agent"))
    U6(("Receive Recommendation"))
    U7(("Approve Action"))
    U8(("Execute Recovery"))
    U9(("View Analytics"))
    U10(("Review Audit"))
  end
  SUP --> U1 & U2 & U3 & U4 & U5 & U6 & U7 & U8
  MGR --> U1 & U9 & U10
  ENG --> U2 & U4 & U8
```

## 4. Class Diagram

```mermaid
classDiagram
  class User { +id +name +role +plantId }
  class Plant { +id +name +location }
  class ProductionOrder { +id +customer +product +quantity +completedQuantity +dueDate +status }
  class Machine { +id +name +type +status +capacityPerHour }
  class FactoryEvent { +id +type +timestamp +source +payload }
  class RiskAssessment { +id +orderId +riskScore +severity +factors }
  class Prediction { +id +modelVersion +delayProbability +failureProbability +anomalyScore }
  class Evidence { +id +source +eventId +confidence }
  class Recommendation { +id +actionType +rationale +confidence }
  class Action { +id +type +status +approvedBy +executedAt }
  class AgentSession { +id +question +response +timestamp }
  Plant --> User
  Plant --> Machine
  Plant --> ProductionOrder
  ProductionOrder --> FactoryEvent
  ProductionOrder --> RiskAssessment
  Machine --> FactoryEvent
  RiskAssessment --> Prediction
  RiskAssessment --> Evidence
  RiskAssessment --> Recommendation
  Recommendation --> Action
  User --> Action
  User --> AgentSession
```

## 5. Sequence — Event to Recommendation

```mermaid
sequenceDiagram
  actor Supervisor
  participant UI as OpsRelay UI
  participant API as API Gateway
  participant ING as Ingestion Lambda
  participant EB as EventBridge
  participant Q as SQS
  participant PROC as Processor Lambda
  participant SM as SageMaker AI
  participant RISK as Risk Engine
  participant AGENT as Strands Agent
  participant DB as DynamoDB
  Supervisor->>UI: Submit factory event
  UI->>API: POST /events
  API->>ING: event payload
  ING->>DB: save event
  ING->>EB: publish FactoryEvent
  EB->>Q: queue event
  Q->>PROC: consume event
  PROC->>DB: load order + machine + history
  PROC->>SM: predict
  SM-->>PROC: ML signals
  PROC->>RISK: calculate score
  RISK-->>PROC: risk + factors
  PROC->>DB: save risk
  UI->>AGENT: ask why / what now
  AGENT->>DB: retrieve evidence
  DB-->>AGENT: evidence
  AGENT-->>UI: grounded recommendation
```

## 6. Activity

```mermaid
flowchart TD
  A([Start]) --> B[Receive Signal] --> C[Normalize] --> D{Valid?}
  D -- No --> DLQ[DLQ] --> Z([End])
  D -- Yes --> E[Store Event] --> F[Update State] --> G[Build Features] --> H[SageMaker Prediction] --> I[Risk Engine] --> J{Risk High?}
  J -- No --> K[Update Dashboard] --> Z
  J -- Yes --> L[Retrieve Evidence] --> M[Strands Agent] --> N[Recommendation] --> O{Approval?}
  O -- No --> P[Wait for Supervisor] --> Z
  O -- Yes --> Q[Execute] --> R[Verify] --> S[Audit] --> K
```

## 7. State Machine — Order

```mermaid
stateDiagram-v2
  [*] --> CREATED
  CREATED --> IN_PROGRESS
  IN_PROGRESS --> AT_RISK
  AT_RISK --> INVESTIGATING
  INVESTIGATING --> RECOVERY_PROPOSED
  RECOVERY_PROPOSED --> RECOVERY_PENDING
  RECOVERY_PENDING --> IN_PROGRESS : rejected
  RECOVERY_PENDING --> RECOVERY_EXECUTING : approved
  RECOVERY_EXECUTING --> IN_PROGRESS : success
  RECOVERY_EXECUTING --> AT_RISK : failure
  IN_PROGRESS --> DELAYED : due exceeded
  IN_PROGRESS --> COMPLETED
  DELAYED --> RECOVERY_PROPOSED
  COMPLETED --> [*]
```

## 8. State Machine — Machine

```mermaid
stateDiagram-v2
  [*] --> AVAILABLE
  AVAILABLE --> RUNNING
  RUNNING --> DEGRADED
  DEGRADED --> RUNNING
  RUNNING --> STOPPED
  DEGRADED --> STOPPED
  STOPPED --> DIAGNOSING
  DIAGNOSING --> AVAILABLE
  DIAGNOSING --> MAINTENANCE
  MAINTENANCE --> AVAILABLE
```

## 9. Deployment

```mermaid
flowchart TB
  U["Supervisor Browser"] --> CF["CloudFront / S3 Website"]
  U --> API["API Gateway"]
  API --> L1["Lambda API"]
  L1 --> DDB["DynamoDB"]
  L1 --> S3["S3"]
  L1 --> EB["EventBridge"] --> Q["SQS"] --> L2["Lambda Processor"]
  L2 --> SM["SageMaker Serverless Endpoint"]
  L1 --> STR["Strands Agent + Bedrock"]
  STR --> DDB
  L1 --> CW["CloudWatch"]
  L2 --> CW
  SM --> CW
```

## 10. ER Diagram

```mermaid
 erDiagram
   PLANT ||--o{ USER : has
   PLANT ||--o{ MACHINE : owns
   PLANT ||--o{ PRODUCTION_ORDER : receives
   PRODUCTION_ORDER ||--o{ FACTORY_EVENT : generates
   MACHINE ||--o{ FACTORY_EVENT : generates
   PRODUCTION_ORDER ||--o{ RISK_ASSESSMENT : evaluated_by
   RISK_ASSESSMENT ||--o{ PREDICTION : uses
   RISK_ASSESSMENT ||--o{ EVIDENCE : supported_by
   RISK_ASSESSMENT ||--o{ RECOMMENDATION : produces
   RECOMMENDATION ||--o{ ACTION : becomes
   USER ||--o{ ACTION : approves
```

## 11. AI/ML Pipeline

```mermaid
flowchart LR
  H[Historical data] --> CLEAN[Clean] --> FE[Features] --> TRAIN[Train] --> EVAL[Evaluate] --> REG[Model Artifact] --> SM[SageMaker Endpoint]
  LIVE[Live event] --> ONLINE[Online features] --> SM
  SM --> P1[Delay probability]
  SM --> P2[Failure probability]
  SM --> P3[Anomaly score]
  P1 & P2 & P3 --> R[Risk Engine]
  R --> A[Strands Agent]
```
