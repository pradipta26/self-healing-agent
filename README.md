**Self-Healing Agent**

Production-Governed Autonomous Remediation Framework for SRE

LLMs suggest. Systems decide. Policies govern. Humans retain control.

⸻

📌 **Overview**

This repository demonstrates a production-safe self-healing agent where autonomy is bounded by policy resolution, execution envelope gating, and per-action readiness checks. It separates execution permission from decision authority and encodes escalation as a structural boundary crossing rather than a model output.
The goal of this project is not to build a “clever bot,” but to design a trustworthy autonomy control plane where:
	•	Autonomous actions are policy-bound.
	•	Escalation semantics are deterministic.
	•	Execution blast radius is explicitly controlled.
	•	Every decision is auditable.
	•	Humans remain in control.

This repository demonstrates a production-style self-healing SRE agent.

The system was originally inspired by enterprise incident management workflows, but all datasets included here are synthetic and generated for demonstration purposes only.

⸻

🎯 **Objectives**
	•	Design a safe autonomy architecture suitable for real production environments.
	•	Separate execution envelope from decision authority.
	•	Encode escalation policies structurally (not via prompts).
	•	Prevent silent autonomy.
	•	Provide audit-ready, explainable decision logs.
	•	Enable progressive rollout (OFF → SHADOW → LIVE).

⸻

🏗 **Architecture**

System Readiness (Execution Mode) controls whether side effects are allowed.
Policy Resolution computes effective autonomy per incident.
Action Readiness validates whether execution is safe right now.
Escalation represents authority boundary crossing — not alerting.

				                           ┌─────────────────────────────┐
				                           │  Incident / Signal Ingest   │
				                           │  (alerts, logs, metrics)    │
				                           └───────────────┬─────────────┘
				                                           │
				                                           ▼
				                           ┌─────────────────────────────┐
				                           │  Suggestion Layer           │
				                           │  (LLM + deterministic rules)│
				                           └───────────────┬─────────────┘
				                                           │
				                                           ▼
				                    ┌────────────────────────────────────────────┐
				                    │            Governance Control Plane        │
				                    │                                            │
				                    │  1. System Readiness → Mode                │
				                    │     OFF | SHADOW | LIVE                    │
				                    │                                            │
				                    │  2. Policy Resolution → Effective Autonomy │
				                    │     L0–L4 + Escalation Floor               │
				                    │                                            │
				                    │  3. Action Readiness → Execution Safety    │
				                    │     rollback • idempotency • tool health   │
				                    └───────────────────┬────────────────────────┘
				                                        │
				                                        ▼
				                         ┌───────────────────────────┐
				                         │ Escalation Router         │
				                         │ NONE | APPROVAL | HANDOFF │
				                         └───────────────┬───────────┘
				                                         │
				                  ┌──────────────────────┼──────────────────────┐
				                  │                      │                      │
				                  ▼                      ▼                      ▼
				           ┌────────────┐        ┌───────────────┐      ┌────────────┐
				           │ Execute    │        │ Human Approval│      │ Human Owns │
				           │ (LIVE only)│        │ Required      │      │ Incident   │
				           └────────────┘        └───────────────┘      └────────────┘
**The system is built around five governance axes:**


⸻

Axis 1 — System Readiness (Execution Mode)

Execution Envelope:
OFF | SHADOW | LIVE

Controls whether side effects are allowed at all.
	•	OFF → No tools. No mutation. Blast radius = 0.
	•	SHADOW → Full planning + validation. No execution. Dry-run only.
	•	LIVE → Real execution permitted (if policy allows).

Mode is computed deterministically using:
	•	Kill switch
	•	Change freeze
	•	Policy engine health
	•	Audit logging health
	•	Control-plane tool readiness

LIVE is a privilege, not a default.

⸻

Axis 2 — Autonomy Level (Decision Authority)

L0–L4

	Level		Meaning
	L0		Recommendation only
	L1		Human approval required
	L2		Rule-based execution
	L3		Execute unless anomaly
	L4		Near-full autonomy

Autonomy is not static. It is computed per incident.

⸻

Axis 3 — Escalation (Boundary Crossing)

Escalation occurs when the system reaches an authority boundary.

Escalation	Meaning
NONE	Proceed
APPROVAL	Human must approve
HANDOFF	Human takes ownership

Escalation is policy-driven — not model-driven.

⸻

Axis 4 — Policy Resolution Engine

Computes Effective Autonomy Level using:
	•	Global caps
	•	Environment caps (prod stricter than dev)
	•	Service caps
	•	Action-type caps
	•	Blast-radius caps
	•	Incident context caps (SEV1, instability, novelty)
	•	Trust posture metrics
	•	Manual autonomy overrides

Output:
	•	Effective Autonomy Level
	•	Escalation Floor
	•	Deny/Allow decision
	•	Machine-readable reason codes

⸻

Axis 5 — Action Readiness Gate

Per-action execution validation:
	•	Tool health
	•	Rollback availability
	•	Idempotency
	•	Target state validation
	•	Recurrence guard
	•	Runtime blast-radius validation

Even if policy allows execution, Action Readiness can escalate or block.

⸻

🔐 Governance Model

The system enforces:

	System Mode
    	↓
	Policy Resolution
    	↓
	Action Readiness
    	↓
	Escalation
    	↓
	Execution (only if LIVE)

Clear separation of:
	•	Execution safety
	•	Decision authority
	•	Governance caps
	•	Runtime safety checks

⸻

🛠 Supported Actions (Initial Scope)
	1.	Kubernetes Pod Restart
	•	Bounded blast radius
	•	Verification after restart
	•	Recurrence guard
	2.	High Disk Space Remediation
	•	Privileged operation
	•	Rollback required
	•	Rollout-gated in production
	3.	Site Failover (GSLB Switch)
	•	Cross-DC blast radius
	•	Default: approval or handoff
	•	Strict governance caps

⸻

📂 **Repository Structure**

policy/                 # YAML policy definitions
autonomicity/
    system_readiness.py
    policy_engine.py
    action_readiness.py
    executor.py
    models.py
examples/
tests/
docs/


⸻

🧪 **Example Scenario**

Mode = LIVE
Service = I2IV (SRE tools)
Action = Pod Restart
Blast Radius = SINGLE_POD

Result:
	•	Effective Level = L3
	•	No escalation
	•	Execute
	•	Decision snapshot logged

⸻

Mode = LIVE
Service = EV6V (Billing)
Action = Site Failover
Severity = SEV1

Result:
	•	Incident context cap → L1
	•	Escalation → HANDOFF
	•	No automatic execution
	•	Human takes ownership

⸻

📊 Decision Logging

Every decision emits a structured snapshot including:
	•	Mode
	•	Effective Autonomy Level
	•	Escalation Floor
	•	Reason Codes
	•	Policy Version
	•	Incident ID
	•	Action Type

This enables:
	•	Audit trails
	•	Postmortem analysis
	•	Trust posture tracking
	•	Escalation tuning

⸻

🧠 **Design Principles**
	•	Prompts are hints. State is truth.
	•	Escalation is a feature, not a failure.
	•	Unsafe paths must not exist in the graph.
	•	Autonomy must decrease under instability.
	•	Human accountability must remain explicit.
	•	Execution Mode and Autonomy Level are orthogonal.

⸻

🚀 **Operational Philosophy**

Default lifecycle: OFF → SHADOW → LIVE

Promotion to LIVE requires:
	•	Stable shadow metrics
	•	Human review
	•	Verified rollback paths
	•	Low novelty and unknown rates

Automatic downgrade is allowed.
Automatic upgrade is not.

⸻

📈 **Production Readiness Goals**

This project aims to demonstrate:
	•	Enterprise-grade escalation semantics
	•	Blast-radius-aware automation
	•	Policy-driven autonomy control
	•	Explicit human-in-the-loop integration
	•	Deterministic system governance
	•	Production observability

⸻

🧭 **Roadmap**
	•	LangGraph state-machine implementation
	•	Decision trace visualization
	•	Replay harness for shadow evaluation
	•	Metrics dashboard for trust posture
	•	Reinforcement learning feedback loop
	•	Canary deployment by Application

⸻

🏁 **Status**

🚧 Active development
🧪 Experimental but governance-focused
🎓 Learning-driven, production-oriented

⸻
