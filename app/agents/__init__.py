"""FinanceGPT multiagent system (LangGraph).

Flow: an orchestrator classifies intent and routes to a single target — the
categorizer (RAG), the tool-calling agent (all data-driven work, via its own
tool loop), the refusal node (off-topic), or the response generator.

Structure:
- constants.py: static configuration values
- types.py: enums and type aliases
- models.py: Pydantic domain models
- state.py: LangGraph AgentState
- graph.py: graph definition
- nodes/: node implementations
- tools/: agent tools (transactions, budgets, goals)
"""
