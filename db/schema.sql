

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
    env TEXT NOT NULL DEFAULT 'PROD',
    service_domain TEXT NOT NULL,
    datacenter TEXT NOT NULL,
    app_name TEXT NOT NULL,
    hosts TEXT[],
    reason TEXT NOT NULL,

    -- Arrays from canonical parsing
    metric_names TEXT[] NOT NULL,
    instances TEXT[] NOT NULL DEFAULT '{}',
    instance_hosts TEXT[] NOT NULL DEFAULT '{}',
    warnings TEXT[] NOT NULL DEFAULT '{}',

    -- Raw source payload
    raw_incident_text TEXT NOT NULL,
    normalized_incident_reason TEXT,
    -- Resolution summary after parsing and enrichment, used for retrieval and explainability
    resolution TEXT,

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

    parent_id BIGINT NOT NULL
        REFERENCES prdb_incident_parent(id)
        ON DELETE CASCADE,

    -- Currently always 1 or 2
    chunk_index INT NOT NULL,

    -- problem / resolution
    chunk_type TEXT NOT NULL,

    -- text used for semantic search
    chunk_text TEXT NOT NULL,

    -- normalized text used to generate embedding
    chunk_text_normalized TEXT,

    -- metadata used for filtering
    service_domain TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    datacenter TEXT NOT NULL,
    incident_type TEXT NOT NULL,
    app_name TEXT NOT NULL,

    -- vector embedding
    embedding VECTOR(1536),

    embedding_model TEXT,

    inserted_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_prdb_chunk UNIQUE(parent_id, chunk_index, chunk_type)
);

CREATE INDEX IF NOT EXISTS idx_prdb_chunk_parent_id
    ON prdb_incident_chunk (parent_id);

CREATE INDEX IF NOT EXISTS idx_prdb_chunk_service_domain
    ON prdb_incident_chunk (service_domain);

CREATE INDEX IF NOT EXISTS idx_prdb_chunk_metric_name
    ON prdb_incident_chunk (metric_name);

CREATE INDEX IF NOT EXISTS idx_prdb_chunk_datacenter
    ON prdb_incident_chunk (datacenter);

CREATE INDEX IF NOT EXISTS idx_prdb_chunk_incident_type
    ON prdb_incident_chunk (incident_type);

CREATE INDEX IF NOT EXISTS idx_prdb_chunk_app_name
    ON prdb_incident_chunk (app_name);

CREATE INDEX IF NOT EXISTS idx_prdb_chunk_service_metric
    ON prdb_incident_chunk (service_domain, metric_name);

-- vector index
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
    service_domain TEXT,
    metric_name TEXT,
    datacenter TEXT,
    app_name TEXT,
    host TEXT,
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

CREATE INDEX IF NOT EXISTS idx_decision_log_metric_name
    ON decision_log (metric_name);

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
    c.parent_id as parent_id,
    p.app_name AS parent_app_name,
    p.service_domain AS parent_service_domain,
    p.metric_names AS parent_metric_name,
    p.datacenter AS parent_datacenter,
    p.host AS parent_host,
    p.incident_type AS parent_incident_type,
    p.reason AS parent_incident_reason,
    p.resolution_summary AS parent_resolution_summary,
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