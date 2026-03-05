# state.py
from __future__ import annotations

from typing import TypedDict, List, Literal, Dict, Any, Optional
from datetime import datetime, timezone


# -----------------------------
# Core enums (existing)
# -----------------------------
Category = Literal["CPU", "MEMORY", "NETWORK", "UNKNOWN"]
Confidence = Literal["HIGH", "MEDIUM", "LOW", "UNKNOWN"]
Actionability = Literal[
    "SAFE_TO_PROPOSE",
    "HUMAN_REQUIRED",
    "INSUFFICIENT_EVIDENCE",
    "CONFLICTING_SIGNALS",
]
RollbackStatus = Literal["SKIPPED", "PLANNED", "EXECUTED", "FAILED"]


class RollbackPlan(TypedDict, total=False):
    status: RollbackStatus
    reason: str
    actions: List[str]          # compensating steps (read-only for now)
    notes: List[str]
    artifacts: Dict[str, Any]   # ids, links, correlation ids, etc.


EscalationType = Literal[
    "NONE",
    "INSUFFICIENT_EVIDENCE",
    "CONFLICTING_SIGNALS",
    "CONFIDENCE_EVIDENCE_MISMATCH",
    "POLICY_VIOLATION",
    "EXECUTION_UNSAFE",
    "HIGH_RISK_ACTION",
    "NOVEL_SITUATION",
]

TriggerCode = Literal[
    "EVIDENCE_EMPTY",
    "EVIDENCE_ID_OUT_OF_RANGE",
    "EVIDENCE_ID_TOO_MANY",
    "EVIDENCE_IDS_NOT_A_LIST",
    "SERVICE_MISMATCH",
    "CONFIDENCE_TOO_HIGH_FOR_WEAK_EVIDENCE",
    "MODEL_OUTPUT_SCHEMA_VIOLATION",
    "AUTONOMY_DISABLED_KILLSWITCH",
    "TOOL_EXECUTION_FAILED",
    "TOOL_TIMEOUT",
    "TOOL_OUTPUT_MALFORMED",
    "TOOL_VERIFICATION_FAILED",
    # Retrieval/RAG triggers (new)
    "RETRIEVAL_EMPTY",
    "RETRIEVAL_LOW_SCORE",
    "RETRIEVAL_CONFLICTING",
    "RERANK_MISMATCH",
    "CONTEXT_TOO_LARGE",
    "CONTEXT_LOW_QUALITY",
    "GROUNDEDNESS_FAILED",
]

HumanRole = Literal["NONE", "INVESTIGATOR", "APPROVER", "SME_REVIEW", "INCIDENT_COMMANDER"]


# -----------------------------
# Week 8+ (Advanced RAG) additions
# -----------------------------
RewriteType = Literal[
    "NONE",
    "DETERMINISTIC_NORMALIZE",
    "DETERMINISTIC_CANONICALIZE",
    "LLM_CONTROLLED",
    "EMBEDDING_EXPANSION",
]

RetrievalStrategy = Literal[
    "VECTOR",
    "LEXICAL",
    "HYBRID",
]

RetrievalStageName = Literal[
    "STAGE1_BROAD",
    "STAGE2_FILTER",
    "STAGE3_RERANK",
]

ContextValidity = Literal[
    "VALID",
    "EMPTY",
    "LOW_QUALITY",
    "CONFLICTING",
    "OVERSIZED",
]

GroundingVerdict = Literal[
    "GROUNDED",
    "PARTIALLY_GROUNDED",
    "NOT_GROUNDED",
]


class QueryRewriteArtifact(TypedDict, total=False):
    """
    Audit-friendly record of query rewriting (deterministic + LLM-controlled).
    Store small strings + metrics, not huge blobs.
    """
    original_query: str
    normalized_query: str
    rewritten_query: str
    rewrite_type: RewriteType
    # Hybrid lexical boosting terms (BM25 / keyword boosts)
    lexical_boost_terms: List[str]
    # Embedding expansion / semantic hints
    embedding_hints: List[str]
    # Safety notes
    safety_notes: List[str]
    # Deterministic facts
    facts: Dict[str, Any]  # e.g., {"added_terms": 3, "removed_terms": 1}


class RetrievedDoc(TypedDict, total=False):
    """
    A single candidate from retrieval.
    Keep it light: identifiers + minimal ranking signals.
    """
    doc_id: str                   # PRDB primary key (preferred)
    source: str                   # e.g., "PRDB"
    incident_id: Optional[str]    # Hawkeye incident id if present
    service: Optional[str]
    env: Optional[str]

    # ranking signals
    vector_score: Optional[float]
    lexical_score: Optional[float]
    rerank_score: Optional[float]

    # minimal snippet for UI/debug (avoid giant bodies in state)
    snippet: Optional[str]
    metadata: Dict[str, Any]      # small fields only (timestamps, tags, etc.)


class RetrievalStageResult(TypedDict, total=False):
    stage: RetrievalStageName
    strategy: RetrievalStrategy
    k: int
    query_used: str
    candidates: List[RetrievedDoc]
    metrics: Dict[str, Any]  # e.g., {"hit_rate": 0.2, "avg_score": 0.41}


class RetrievalConfidenceObject(TypedDict):
    """
    RCO = structured, deterministic summary of retrieval quality + risk.
    This becomes a first-class input to Escalation Policy (Topic 8).
    """
    # Overall assessment
    is_sufficient: bool
    confidence: Confidence                 # retrieval confidence (not model confidence)
    validity: ContextValidity              # empty/low quality/conflicting/ok

    # Explainability
    summary: str
    signals: Dict[str, Any]                # counts + small metrics (audit-safe)

    # References (no huge payloads)
    top_doc_ids: List[str]                 # PRDB primary keys used for grounding
    top_incident_ids: List[str]            # if available
    stage_results: List[RetrievalStageResult]


class ContextValidationResult(TypedDict):
    ok: bool
    validity: ContextValidity
    issues: List[str]
    facts: Dict[str, Any]  # {"doc_count": 4, "conflict_pairs": 1, "token_estimate": 3200}


class GroundingCheckResult(TypedDict):
    """
    Structured grounding: does the answer/proposal cite evidence?
    """
    verdict: GroundingVerdict
    ok: bool
    missing_claims: List[str]
    used_evidence_doc_ids: List[str]
    notes: List[str]


# -----------------------------
# Existing decision objects (kept)
# -----------------------------
class DecisionSnapshot(TypedDict):
    decision_id: str  # “embedded copy for portability when handing off decision object”
    policy_version: str

    # Expand routing from 2-way (week-3) to 4-way
    route: Literal["PROPOSE", "HITL_APPROVAL", "HITL_INVESTIGATION", "HITL_SME_REVIEW"]
    confidence: Confidence
    actionability: Actionability

    escalation_type: EscalationType
    trigger_codes: List[TriggerCode]
    service_match: bool
    required_human_role: HumanRole

    # compact, audit-friendly details
    summary: str                 # one-liner why we routed this way
    facts: Dict[str, Any]        # small deterministic facts (counts, booleans)


class DecisionLog(TypedDict):
    """
    Immutable commit record written exactly once per committed decision.
    This is NOT a running list of snapshots; it is the audit artifact used for later reconstruction.
    """
    # Identity / correlation
    decision_id: str
    trace_id: str
    incident_id: str

    # Execution mode / safety gates at decision time
    autonomy_mode: Literal["OFF", "SHADOW", "LIVE"]
    kill_switch_state: Literal["ENABLED", "DISABLED"]
    dry_run: bool  # derived from autonomy_mode

    # Decision outcome (overlaps with DecisionSnapshot by design)
    policy_version: str
    route: Literal["PROPOSE", "HITL_APPROVAL", "HITL_INVESTIGATION", "HITL_SME_REVIEW"]
    confidence: Confidence
    actionability: Actionability
    escalation_type: EscalationType

    # Policy gates (include blast radius checks here)
    policy_checks: Dict[str, bool]

    # Evidence and intent references (store ids/hashes, not raw text)
    evidence_ref_ids: List[int]
    tool_plan_hash: Optional[str]

    # RAG / retrieval references (new)
    rco_summary: Optional[str]
    retrieved_doc_ids: List[str]
    query_rewrite: Optional[QueryRewriteArtifact]

    # Metadata
    timestamp_utc: str          # ISO-8601 (e.g., datetime.now(timezone.utc).isoformat())
    schema_version: str         # e.g. "v2"


# -----------------------------
# Input / output contracts (existing, lightly expanded)
# -----------------------------
class IncidentInput(TypedDict):
    incident_text: str
    service: str
    env: Literal["PROD", "NONPROD"]


class ModelOutput(TypedDict, total=False):
    category: Category
    confidence: Confidence
    actionability: Actionability
    description: str
    evidence_ids: List[int]
    remediation: List[str]

    # Optional: structured grounding hooks (if your prompt returns them)
    cited_doc_ids: List[str]  # PRDB doc ids used
    hypotheses: List[str]


class ProposalOutput(TypedDict):
    service: str
    env: Literal["PROD", "NONPROD"]
    category: Category
    summary: str
    evidence: List[str]
    proposals: List[str]
    approval_required: bool


class ApprovalRequest(TypedDict):
    request_id: str
    decision: DecisionSnapshot
    service: str
    env: Literal["PROD", "NONPROD"]
    proposed_actions: List[str]
    evidence: List[str]
    approval_question: str
    safety_notes: List[str]


class InvestigationRequest(TypedDict):
    request_id: str
    decision: DecisionSnapshot
    service: str
    env: Literal["PROD", "NONPROD"]
    suspected_issue: str
    trigger_codes: List[TriggerCode]
    evidence: List[str]
    suggested_actions: List[str]
    notes: List[str]
    questions: List[str]
    data_to_collect: List[str]
    rollback_plan: Dict[str, Any]


class SMEReviewRequest(TypedDict):
    request_id: str
    decision: DecisionSnapshot
    service: str
    env: Literal["PROD", "NONPROD"]
    summary: str
    evidence: List[str]
    hypotheses: List[str]
    open_risks: List[str]


# -----------------------------
# Tooling & execution safety (existing)
# -----------------------------
class ToolCall(TypedDict):
    tool_name: str
    args: Dict[str, Any]
    idempotency_key: str


class ToolResult(TypedDict, total=False):
    ok: bool
    raw: Dict[str, Any]
    error: str


class VerificationResult(TypedDict):
    ok: bool
    details: Dict[str, Any]


class DiagnosticsInput(TypedDict):
    service: str
    env: Literal["PROD", "NONPROD"]
    checks: List[Literal["CPU", "MEMORY", "LATENCY", "ERROR_RATE", "DEPENDENCIES"]]


class ToolMeta(TypedDict, total=False):
    trace_id: str
    incident_id: str
    decision_id: str
    tool_step: int
    attempt: int


BlastRadiusScope = Literal["SINGLE_TARGET", "SERVICE", "CLUSTER", "REGION", "GLOBAL"]


class BlastRadiusAssessment(TypedDict, total=False):
    """
    Computed from the tool plan prior to execution.
    Keep this small; the DecisionLog stores policy_check outcomes, not all analysis text.
    """
    scope: BlastRadiusScope
    target_count: int
    reversible: bool
    notes: List[str]


# -----------------------------
# The main AgentState (updated)
# -----------------------------
class AgentState(TypedDict, total=False):
    # Inputs
    incident_raw: str
    incident: IncidentInput

    # Correlation / identity
    trace_id: str
    incident_id: str

    # IMPORTANT: PRDB primary key for the Hawkeye incident when 1:1 exists
    prdb_id: Optional[str]  # keep optional because not all PRDB rows come from HE

    decision_id: Optional[str]        # authoritative correlation id for this run's committed decision
    decision_log_id: Optional[str]    # storage id / ref returned by the log sink (if any)

    # Safety / rollout
    autonomy_mode: Literal["OFF", "SHADOW", "LIVE"]
    kill_switch_state: Literal["ENABLED", "DISABLED"]
    blast_radius: Optional[BlastRadiusAssessment]
    event_ids: List[str]              # references to persisted events / logs (do not store large blobs in state)

    # -------------------------
    # RAG / retrieval pipeline (new)
    # -------------------------
    query_rewrite: QueryRewriteArtifact
    retrieval_strategy: RetrievalStrategy
    retrieval_stages: List[RetrievalStageResult]  # broad -> filter -> rerank
    rco: RetrievalConfidenceObject                # Stage 4 — Retrieval Confidence Object
    context_validation: ContextValidationResult   # Topic 5/6 guardrail
    grounding_check: GroundingCheckResult         # Topic 7 Structured Grounding

    # Derived / selected evidence for prompts and outputs
    evidence_candidates: List[RetrievedDoc]        # retrieved docs (light)
    filtered_evidence: List[str]                   # final text snippets used to ground (kept small)
    evidence_valid: bool

    # Model raw + parsed output
    llm_raw: str
    model_output: ModelOutput

    # Decisioning
    decision: DecisionSnapshot
    proposal_output: ProposalOutput

    # HITL routes
    approval_request: ApprovalRequest
    investigation_request: InvestigationRequest
    sme_review_request: SMEReviewRequest

    # Tooling & execution safety
    tool_step: int
    attempt: int
    tool_retry_decision: Literal["RETRY_TOOL", "NO_RETRY"]
    tool_call: ToolCall
    tool_result: ToolResult
    tool_trigger_codes: List[TriggerCode]
    verification_result: VerificationResult
    diagnostics_input: DiagnosticsInput
    rollback_plan: RollbackPlan

    # Audit / debug breadcrumbs
    warnings: List[str]
    trace: List[str]

    # Error handling
    error_flag: bool
    error_message: Optional[str]
    

# -----------------------------
# Helpers (optional but handy)
# -----------------------------
def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()