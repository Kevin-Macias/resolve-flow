"""Constructor-only overlay for the StateGraph API used by ResolveFlow.

Builder and compiled methods are described by workflow/langgraph_types.py.
Keep this signature aligned with the installed LangGraph constructor.
"""

from typing import Any

class StateGraph:
    def __init__(self, state_schema: type[Any], *, input_schema: type[Any]) -> None: ...
