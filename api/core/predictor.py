from __future__ import annotations

import json
import os
from typing import Any

try:
    import boto3
except Exception:  # pragma: no cover
    boto3 = None


def heuristic_prediction(features: dict[str, Any]) -> dict[str, float]:
    downtime = min(1.0, float(features.get("downtimeMinutes", 0)) / 180.0)
    rework = min(1.0, float(features.get("reworkRate", 0)))
    material = min(1.0, float(features.get("materialDelayHours", 0)) / 12.0)
    remaining = min(1.0, float(features.get("remainingRatio", 0)))
    due = min(1.0, max(0.0, (24.0 - float(features.get("dueHours", 24))) / 24.0))
    machine_bad = 1.0 if features.get("machineStatus") == "STOPPED" else 0.55 if features.get("machineStatus") == "DEGRADED" else 0.0
    delay = min(0.99, 0.08 + 0.28 * downtime + 0.20 * rework + 0.16 * material + 0.16 * remaining + 0.08 * due + 0.18 * machine_bad)
    failure = min(0.99, 0.05 + 0.45 * downtime + 0.35 * machine_bad + 0.15 * rework)
    anomaly = min(0.99, 0.10 + 0.55 * downtime + 0.25 * rework + 0.15 * material)
    return {"delayProbability": round(delay, 4), "failureProbability": round(failure, 4), "anomalyScore": round(anomaly, 4)}


class SageMakerPredictor:
    def __init__(self) -> None:
        self.enabled = os.getenv("SAGEMAKER_ENABLED", "false").lower() == "true"
        self.endpoint = os.getenv("SAGEMAKER_ENDPOINT_NAME", "").strip()
        region = os.getenv("AWS_REGION", "ap-south-1")
        self.client = boto3.client("sagemaker-runtime", region_name=region) if boto3 else None

    def predict(self, features: dict[str, Any]) -> dict[str, float]:
        if not self.enabled or not self.endpoint or not self.client:
            return heuristic_prediction(features)
        try:
            response = self.client.invoke_endpoint(
                EndpointName=self.endpoint,
                ContentType="application/json",
                Accept="application/json",
                Body=json.dumps(features).encode("utf-8"),
            )
            body = response["Body"].read().decode("utf-8")
            result = json.loads(body)
            return {
                "delayProbability": float(result["delayProbability"]),
                "failureProbability": float(result["failureProbability"]),
                "anomalyScore": float(result["anomalyScore"]),
            }
        except Exception:
            return heuristic_prediction(features)
