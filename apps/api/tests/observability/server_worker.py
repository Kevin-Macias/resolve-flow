"""Disposable server process used to verify the supported output configuration."""

import socket
import sys

import uvicorn
from fastapi import Request

from api.main import create_app
from api.observability.config import LOG_CONFIG, configure_logging

app = create_app()


@app.post("/failure/{item}")
async def fail(item: str, request: Request) -> None:
    body = await request.body()
    raise RuntimeError(f"{item}:{body.decode()}")


if __name__ == "__main__":
    configure_logging()
    listener = socket.socket(fileno=int(sys.argv[1]))
    server = uvicorn.Server(
        uvicorn.Config(app, log_config=LOG_CONFIG, access_log=False)
    )
    server.run(sockets=[listener])
