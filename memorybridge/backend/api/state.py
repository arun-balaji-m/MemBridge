"""
state.py — MemoryBridge Phase 2
Module-level dict that holds application-wide singletons
(embedding model, start time). Populated by main.py lifespan.
Routers import this directly to access app_state["model"].
"""

app_state: dict = {}
