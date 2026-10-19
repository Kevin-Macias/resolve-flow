"""Run the API with the supported metadata-only logging configuration."""

import argparse
import os

import uvicorn

from api.observability.config import LOG_CONFIG, configure_logging


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    args = parser.parse_args()
    configure_logging()
    uvicorn.run(
        "api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_config=LOG_CONFIG,
        access_log=False,
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
