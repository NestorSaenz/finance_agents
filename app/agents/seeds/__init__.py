"""Seeds for agent initialization.

This module contains seed data for initializing the agent system,
including category examples for embedding indexing.
"""

from app.agents.seeds.category_examples import (
    CATEGORY_EXAMPLES,
    get_all_examples,
    get_category_count,
    get_example_count,
)

__all__ = [
    "CATEGORY_EXAMPLES",
    "get_all_examples",
    "get_category_count",
    "get_example_count",
]
