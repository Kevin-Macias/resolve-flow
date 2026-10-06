"""The LangGraph API subset used by ResolveFlow.

Upstream overloads contain unspecified generic parameters. Cast the builder
once at the library boundary; keep callers checked against these signatures.
This is a static view of the original objects, not a runtime wrapper.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Literal, Protocol

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command, StateSnapshot


class WorkflowGraph[InputT](Protocol):
    async def ainvoke(
        self,
        input: InputT | Command[Any] | None,
        config: RunnableConfig | None = None,
        *,
        durability: Literal["sync", "async", "exit"] | None = None,
    ) -> dict[str, Any]: ...

    def astream(
        self,
        input: InputT | Command[Any] | None,
        config: RunnableConfig | None = None,
        *,
        stream_mode: Literal["updates"],
    ) -> AsyncIterator[dict[str, Any]]: ...

    async def aget_state(self, config: RunnableConfig) -> StateSnapshot: ...

    async def aupdate_state(
        self,
        config: RunnableConfig,
        values: dict[str, Any],
        as_node: str | None = None,
    ) -> RunnableConfig: ...


class WorkflowBuilder[StateT, InputT, UpdateT](Protocol):
    def add_node(
        self,
        node: str,
        action: Callable[[StateT], UpdateT | Awaitable[UpdateT]],
    ) -> object: ...

    def add_edge(self, start_key: str, end_key: str) -> object: ...

    def add_conditional_edges(
        self,
        source: str,
        path: Callable[[StateT], str],
        path_map: dict[str, str] | None = None,
    ) -> object: ...

    def compile(
        self, *, checkpointer: BaseCheckpointSaver[str]
    ) -> WorkflowGraph[InputT]: ...
