# 3-minute First Commit demo

## 0:00–0:20 — The problem

"Factories already produce operational signals. The problem is that those signals are fragmented across operators, machines, quality, materials and order systems. OpsRelay turns those signals into a single promise-protection loop."

## 0:20–0:45 — Live risk

Open the Promise Board.

Select `ORD-1048`.

Point to the risk score, due buffer, stopped machine and rework evidence.

## 0:45–1:10 — Inject a real signal

Open Signal Stream.

Publish:

`CNC-04 stopped. Coolant pressure low."

Show the signal appearing and the order risk updating.

## 1:10–1:45 — SageMaker prediction

Open the order details/risk view.

Say:

"The deterministic risk engine owns the operational score. SageMaker AI contributes probabilistic delay, failure and anomaly signals. This keeps the control score explainable while still using ML."

## 1:45–2:20 — Agent investigation

Open Operations Agent.

Ask:

`Why is ORD-1048 at risk, and what should we do now?`

Show evidence and recovery recommendation.

## 2:20–2:40 — Human approval

Open Recovery Queue.

Approve the recommendation.

Show the order moving to another compatible machine and the risk dropping.

## 2:40–2:55 — AWS architecture

Quickly show the architecture:

`API Gateway → Lambda → EventBridge → SQS → Processor Lambda → SageMaker AI → Risk Engine → Strands Agent → DynamoDB / Action`

## 2:55–3:00 — Close

"OpsRelay does not replace the factory's ERP. It adds the missing decision layer: Signal → Evidence → Risk → Action."
