"""Concrete client implementations of the shared interfaces.

Active stack:
- VertexLLMClient: LLM via Vertex AI Gemini (primary)
- GroqLLMClient: LLM via Groq (cross-provider fallback)
- FallbackLLMClient: ordered chain over the above
- TracedLLMClient: Langfuse-tracing decorator for any LLM client
- VertexEmbeddingClient: embeddings via Vertex AI (gemini-embedding-001, 768 dims)
- PgVectorStore: vector storage via Postgres + pgvector (Supabase)
- SupabaseClient: database via Supabase (PostgreSQL)

Clients are imported lazily in ``app/shared/dependencies.py``; this module only
documents the active set (no eager re-exports, so an unused provider's SDK need
not be installed).
"""
