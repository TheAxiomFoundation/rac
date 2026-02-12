"""Inflation indexing system for RAC.

This module implements the three-tier parameter resolution:
1. PUBLISHED - Official government values (e.g., IRS Rev. Proc.)
2. PROJECTED - Our calculations using statute + forecasts
3. CALCULATED - On-the-fly from base year + latest index
"""

from .index_store import IndexStore
from .resolver import IndexedValue, ParameterResolver

__all__ = ["IndexStore", "ParameterResolver", "IndexedValue"]
