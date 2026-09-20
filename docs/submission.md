# Submission write-up draft

## Project

OpsRelay — Zero-ERP Factory Execution Copilot

## Problem

Manufacturing SMEs often operate with fragmented operational information across spreadsheets, machine events, operator notes, maintenance events and quality records. The result is a late discovery problem: a delivery promise can become unsafe before the supervisor has a complete explanation of why.

## Solution

OpsRelay is an event-driven decision layer that ingests factory signals, maintains order and machine state, predicts delivery risk with SageMaker AI, calculates an authoritative operational risk score, grounds a Strands Agent response in observable evidence, and routes recovery actions through a human approval gate.

## AWS usage

- API Gateway for the application API
- Lambda for API, ingestion and processing
- EventBridge for normalized factory event routing
- SQS + DLQ for reliable asynchronous processing
- DynamoDB for operational state
- S3 for raw event archival
- SageMaker AI for delay/failure/anomaly prediction
- Bedrock through Strands Agents for operational reasoning
- Cognito-ready identity layer
- CloudWatch for logs, metrics and the operational dashboard

## Innovation

OpsRelay does not require replacing a factory's existing ERP or introducing a new shop-floor execution system. It adds a thin decision layer above existing workflows and focuses on the highest-value question: which customer promise is at risk, why, and what action can recover it now?

## Responsible AI

The LLM is not the authority for the numeric risk score and cannot bypass the human approval gate for consequential actions. Predictions are shown as probabilities, evidence is displayed to users, and recovery actions are audited.

## Demo

Use `docs/demo-script.md` for the three-minute video flow.
