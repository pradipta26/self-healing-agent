

-- PostgreSQL + pgvector schema for Self-Healing Agent
-- Purpose:
--   1) Store parent incident records (source-of-truth)
--   2) Store retrievable child chunks with embeddings
--   3) Store immutable decision-log audit records

CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- 1. Parent incident table
-- ============================================================
CREATE TABLE IF NOT EXISTS prdb_incident_parent (
    id BIGSERIAL PRIMARY KEY,

    -- External/source identifiers
    source_incident_id TEXT,
    source_system TEXT NOT NULL DEFAULT 'synthetic',

    -- Canonical parsed fields
    incident_type TEXT NOT NULL,
    env TEXT NOT NULL,
    service_domain TEXT NOT NULL,
    datacenter TEXT NOT NULL,
    app_name TEXT NOT NULL,
    host TEXT,
    reason TEXT NOT NULL,

    -- Arrays from canonical parsing
    metric_names TEXT[] NOT NULL DEFAULT '{}',
    instances TEXT[] NOT NULL DEFAULT '{}',
    instance_hosts TEXT[] NOT NULL DEFAULT '{}',
    warnings TEXT[] NOT NULL DEFAULT '{}',

    -- Raw source payload
    raw_incident_text TEXT NOT NULL,
    normalized_incident_text TEXT,

    -- Optional remediation / PRDB-style enrichment
    issue_desc TEXT,
    root_cause TEXT,
    mitigation TEXT,
    fortification TEXT,
    resolution_summary TEXT,

    -- Metadata
    payload_hash TEXT,
    source_created_at TIMESTAMPTZ,
    source_updated_at TIMESTAMPTZ,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_prdb_incident_parent_source UNIQUE (source_system, source_incident_id)
);

CREATE INDEX IF NOT EXISTS idx_prdb_parent_service_domain
    ON prdb_incident_parent (service_domain);

CREATE INDEX IF NOT EXISTS idx_prdb_parent_datacenter
    ON prdb_incident_parent (datacenter);

CREATE INDEX IF NOT EXISTS idx_prdb_parent_incident_type
    ON prdb_incident_parent (incident_type);

CREATE INDEX IF NOT EXISTS idx_prdb_parent_env
    ON prdb_incident_parent (env);

CREATE INDEX IF NOT EXISTS idx_prdb_parent_app_name
    ON prdb_incident_parent (app_name);

CREATE INDEX IF NOT EXISTS idx_prdb_parent_inserted_at
    ON prdb_incident_parent (inserted_at DESC);


-- ============================================================
-- 2. Child chunk table for retrieval
--    One parent incident can produce multiple retrievable chunks.
-- ============================================================
CREATE TABLE IF NOT EXISTS prdb_incident_chunk (
    id BIGSERIAL PRIMARY KEY,
    parent_id BIGINT NOT NULL REFERENCES prdb_incident_parent(id) ON DELETE CASCADE,

    -- Chunk identity
    chunk_index INT NOT NULL,
    chunk_type TEXT NOT NULL,

    -- Retrieval payload
    chunk_text TEXT NOT NULL,
    chunk_text_normalized TEXT,

    -- Metadata duplicated intentionally for fast filtering
    source_incident_id TEXT,
    incident_type TEXT NOT NULL,
    env TEXT NOT NULL,
    service_domain TEXT NOT NULL,
    datacenter TEXT NOT NULL,
    app_name TEXT NOT NULL,
    host TEXT,
    metric_names TEXT[] NOT NULL DEFAULT '{}',

    -- Embedding column (adjust dimension to the model you choose)
    embedding VECTOR(1536),

    -- Optional sparse / lexical support placeholders
    lexical_document TEXT,

    -- Audit metadata
    embedding_model TEXT,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_prdb_incident_chunk_parent_chunk UNIQUE (parent_id, chunk_index, chunk_type)
);

CREATE INDEX IF NOT EXISTS idx_prdb_chunk_parent_id
    ON prdb_incident_chunk (parent_id);

CREATE INDEX IF NOT EXISTS idx_prdb_chunk_service_domain
    ON prdb_incident_chunk (service_domain);

CREATE INDEX IF NOT EXISTS idx_prdb_chunk_datacenter
    ON prdb_incident_chunk (datacenter);

CREATE INDEX IF NOT EXISTS idx_prdb_chunk_incident_type
    ON prdb_incident_chunk (incident_type);

CREATE INDEX IF NOT EXISTS idx_prdb_chunk_env
    ON prdb_incident_chunk (env);

CREATE INDEX IF NOT EXISTS idx_prdb_chunk_app_name
    ON prdb_incident_chunk (app_name);

-- Approximate nearest-neighbor index for cosine similarity
-- Note: create after enough rows exist for better performance.
CREATE INDEX IF NOT EXISTS idx_prdb_chunk_embedding_cosine
    ON prdb_incident_chunk
    USING hnsw (embedding vector_cosine_ops);


-- ============================================================
-- 3. Immutable decision log table
--    One row per committed decision / routed outcome.
-- ============================================================
CREATE TABLE IF NOT EXISTS decision_log (
    id BIGSERIAL PRIMARY KEY,

    -- Identity / correlation
    decision_id TEXT NOT NULL UNIQUE,
    trace_id TEXT NOT NULL,
    incident_id TEXT NOT NULL,
    parent_incident_id BIGINT REFERENCES prdb_incident_parent(id) ON DELETE SET NULL,

    -- Runtime mode / safety state
    autonomy_mode TEXT NOT NULL,
    kill_switch_state TEXT NOT NULL,
    dry_run BOOLEAN NOT NULL,

    -- Decision outcome
    policy_version TEXT NOT NULL,
    route TEXT NOT NULL,
    confidence TEXT NOT NULL,
    actionability TEXT NOT NULL,
    escalation_type TEXT NOT NULL,
    required_human_role TEXT,
    service_match BOOLEAN,

    -- Canonical context at decision time
    incident_type TEXT,
    env TEXT,
    service_domain TEXT,
    datacenter TEXT,
    app_name TEXT,
    reason TEXT,

    -- Explainability / audit
    trigger_codes TEXT[] NOT NULL DEFAULT '{}',
    warnings TEXT[] NOT NULL DEFAULT '{}',
    summary TEXT,
    facts JSONB NOT NULL DEFAULT '{}'::jsonb,
    policy_checks JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Evidence / retrieval references
    evidence_ref_ids INT[] NOT NULL DEFAULT '{}',
    retrieved_doc_ids TEXT[] NOT NULL DEFAULT '{}',
    rco_summary TEXT,
    query_rewrite JSONB,

    -- Tool / execution references
    tool_plan_hash TEXT,

    -- Raw committed artifacts for auditability
    structured_input JSONB,
    decision_snapshot JSONB NOT NULL,

    -- Metadata
    schema_version TEXT NOT NULL,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_decision_log_trace_id
    ON decision_log (trace_id);

CREATE INDEX IF NOT EXISTS idx_decision_log_incident_id
    ON decision_log (incident_id);

CREATE INDEX IF NOT EXISTS idx_decision_log_parent_incident_id
    ON decision_log (parent_incident_id);

CREATE INDEX IF NOT EXISTS idx_decision_log_route
    ON decision_log (route);

CREATE INDEX IF NOT EXISTS idx_decision_log_escalation_type
    ON decision_log (escalation_type);

CREATE INDEX IF NOT EXISTS idx_decision_log_service_domain
    ON decision_log (service_domain);

CREATE INDEX IF NOT EXISTS idx_decision_log_datacenter
    ON decision_log (datacenter);

CREATE INDEX IF NOT EXISTS idx_decision_log_timestamp_utc
    ON decision_log (timestamp_utc DESC);

CREATE INDEX IF NOT EXISTS idx_decision_log_facts_gin
    ON decision_log USING GIN (facts);

CREATE INDEX IF NOT EXISTS idx_decision_log_policy_checks_gin
    ON decision_log USING GIN (policy_checks);


-- ============================================================
-- 4. Helpful view: retrieval chunk joined to parent context
-- ============================================================
CREATE OR REPLACE VIEW vw_prdb_chunk_with_parent AS
SELECT
    c.id AS chunk_id,
    c.parent_id,
    p.source_incident_id,
    p.source_system,
    p.incident_type AS parent_incident_type,
    p.env AS parent_env,
    p.service_domain AS parent_service_domain,
    p.datacenter AS parent_datacenter,
    p.app_name AS parent_app_name,
    p.reason AS parent_reason,
    p.root_cause,
    p.mitigation,
    p.fortification,
    c.chunk_index,
    c.chunk_type,
    c.chunk_text,
    c.chunk_text_normalized,
    c.embedding_model,
    c.inserted_at AS chunk_inserted_at,
    p.inserted_at AS parent_inserted_at
FROM prdb_incident_chunk c
JOIN prdb_incident_parent p
  ON p.id = c.parent_id;