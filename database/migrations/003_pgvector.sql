-- Migration 003: pgvector store (replaces Pinecone).
--
-- Stores embeddings inside Supabase/Postgres. Dimension is 768 to match the
-- Vertex Gemini embedding provider (gemini-embedding-001, output 768). If you
-- use a different embedding model, change the dimension here AND
-- EMBEDDING_DIMENSION in settings, then re-seed.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS vector_embeddings (
    id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL DEFAULT '',
    embedding vector(768) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vector_embeddings_namespace
    ON vector_embeddings (namespace);

-- Approximate-nearest-neighbour index for cosine distance.
CREATE INDEX IF NOT EXISTS idx_vector_embeddings_cosine
    ON vector_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Similarity search. Returns cosine SIMILARITY (1 = identical), so callers can
-- keep using a `score >= threshold` check (same semantics as Pinecone).
-- `metadata_filter` uses JSONB containment (e.g. {"user_id": "..."}).
CREATE OR REPLACE FUNCTION match_vectors(
    query_embedding vector(768),
    match_namespace TEXT DEFAULT '',
    match_count INT DEFAULT 5,
    metadata_filter JSONB DEFAULT '{}'
)
RETURNS TABLE (id TEXT, similarity FLOAT, metadata JSONB)
LANGUAGE sql STABLE
AS $$
    SELECT
        ve.id,
        1 - (ve.embedding <=> query_embedding) AS similarity,
        ve.metadata
    FROM vector_embeddings ve
    WHERE (match_namespace = '' OR ve.namespace = match_namespace)
      AND ve.metadata @> metadata_filter
    ORDER BY ve.embedding <=> query_embedding
    LIMIT match_count;
$$;
