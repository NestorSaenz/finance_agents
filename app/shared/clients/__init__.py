"""Concrete implementations of interfaces.

Current implementations:
- GroqLLMClient: LLM using Groq (Llama 3.3/3.1) - Free tier
- GeminiLLMClient: LLM using Google Gemini (1.5 Pro/Flash) - Pro quality
- CohereLLMClient: LLM using Cohere Command R+ - Fallback
- CohereEmbeddingClient: Embeddings using Cohere Embed v3
- PineconeVectorStore: Vector storage using Pinecone Serverless
- SupabaseClient: Database using Supabase (PostgreSQL)

To add a new provider:
1. Create a new client file (e.g., openai_client.py)
2. Implement the corresponding interface
3. Register it in dependencies.py
"""

from app.shared.clients.cohere_embedding import CohereEmbeddingClient
from app.shared.clients.cohere_llm import CohereLLMClient
from app.shared.clients.gemini_llm import GeminiLLMClient
from app.shared.clients.groq_llm import GroqLLMClient
from app.shared.clients.pinecone_store import PineconeVectorStore
from app.shared.clients.supabase_client import SupabaseClient

__all__ = [
    "GroqLLMClient",
    "GeminiLLMClient",
    "CohereLLMClient",
    "CohereEmbeddingClient",
    "PineconeVectorStore",
    "SupabaseClient",
]
