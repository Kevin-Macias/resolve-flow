"""Crash and recover an approved simulation in separate interpreter processes."""

import asyncio
import os
import sys
from typing import Never
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.support.actions import SupportActions
from api.support.execution import DurableSimulation
from api.workflow.actions import CreateTicketArguments, ProposedAction
from api.workflow.approval import ApprovalDecision, ApprovalReply
from api.workflow.execution import (
    SimulatedCreateTicketTool,
    SimulatedTicketResult,
    ToolExecutionResult,
)


async def main() -> None:
    url, schema, report_id, run_id, raw_reply, mode = sys.argv[1:]
    engine = create_async_engine(
        url.replace("postgresql://", "postgresql+psycopg://"),
        connect_args={"options": f"-csearch_path={schema},public"},
    )
    service = SupportActions(
        async_sessionmaker(engine, expire_on_commit=False), url, f"{schema}_cp"
    )
    original = DurableSimulation.complete

    async def crash(*args: object, **kwargs: object) -> Never:
        os._exit(73)

    if mode == "before_effect":
        DurableSimulation.destination = crash
    elif mode == "after_effect":
        DurableSimulation.complete = crash
    elif mode == "during_effect":

        class ExitTool(SimulatedCreateTicketTool):
            async def create_ticket(
                self,
                arguments: CreateTicketArguments,
                idempotency_key: UUID,
            ) -> SimulatedTicketResult:
                await super().create_ticket(arguments, idempotency_key)
                os._exit(73)

        service.tool = ExitTool
    elif mode == "after_result":

        async def after_result(
            self: DurableSimulation,
            proposal: ProposedAction,
            approval: ApprovalDecision,
            result: ToolExecutionResult,
        ) -> None:
            await original(self, proposal, approval, result)
            os._exit(73)

        DurableSimulation.complete = after_result
    try:
        reply = ApprovalReply.model_validate_json(raw_reply)
        command = service.recover if mode == "recover" else service.decide
        result = await command("support", UUID(report_id), UUID(run_id), reply)
        print(result.model_dump_json())
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
