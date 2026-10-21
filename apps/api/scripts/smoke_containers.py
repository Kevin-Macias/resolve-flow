"""Build and verify an isolated Compose stack, then delete only its own data."""

import json
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]


def free_ports() -> tuple[int, int, int]:
    sockets = [socket.socket() for _ in range(3)]
    try:
        for listener in sockets:
            listener.bind(("127.0.0.1", 0))
        return (
            sockets[0].getsockname()[1],
            sockets[1].getsockname()[1],
            sockets[2].getsockname()[1],
        )
    finally:
        for listener in sockets:
            listener.close()


def http_status(port: int, path: str, payload: dict[str, str] | None = None) -> int:
    request = Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"} if payload is not None else {},
    )
    try:
        with urlopen(request, timeout=8) as response:
            return response.status
    except HTTPError as error:
        return error.code


def wait_for_status(port: int, path: str, expected: int) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if http_status(port, path) == expected:
                return
        except (URLError, OSError):
            pass
        time.sleep(0.25)
    raise RuntimeError(f"Probe {path} did not reach HTTP {expected}")


def main() -> None:
    project = f"rf-smoke-{uuid4().hex[:12]}"
    db_port, api_port, web_port = free_ports()
    settings = {
        "COMPOSE_PROJECT_NAME": project,
        "POSTGRES_VOLUME_NAME": f"{project}-data",
        "POSTGRES_DB": "smoke",
        "POSTGRES_USER": "smoke",
        "POSTGRES_PASSWORD": "isolated-smoke-only",
        "POSTGRES_PORT": str(db_port),
        "API_PORT": str(api_port),
        "WEB_PORT": str(web_port),
        "WEB_ORIGIN": f"http://127.0.0.1:{web_port}",
        "VITE_API_URL": f"http://127.0.0.1:{api_port}",
        "CORS_ORIGINS": f"http://127.0.0.1:{web_port}",
        "AUTH_MODE": "password",
        "INTAKE_PROVIDER_MODE": "offline",
        "EVIDENCE_PROVIDER_MODE": "offline",
        "OPENAI_API_KEY": "",
        "OPENAI_MODEL": "",
        "EVIDENCE_OPENAI_MODEL": "",
        "MODEL_PRICING": "",
        "REQUEST_LIMITS": "{}",
        "DEMO_TOKEN_USER_IDS": "{}",
        "DEMO_SUPPORT_ACCOUNT_IDS": "{}",
    }
    environment = {**os.environ, **settings}
    with tempfile.TemporaryDirectory(prefix="resolveflow-smoke-") as directory:
        folder = Path(directory)
        env_file = folder / "stack.env"
        env_file.write_text(
            "\n".join(f"{key}={value}" for key, value in settings.items())
        )
        failure_file = folder / "failure.yaml"
        failure_file.write_text(
            "services:\n  initialize:\n    environment:\n      RESOLVEFLOW_API_ROOT: /missing-migrations\n"
        )
        base = [
            "docker",
            "compose",
            "-p",
            project,
            "--env-file",
            str(env_file),
            "-f",
            str(ROOT / "docker-compose.yml"),
        ]

        def compose(
            *arguments: str, check: bool = True, fail_init: bool = False
        ) -> subprocess.CompletedProcess[str]:
            command = (
                base
                + (["-f", str(failure_file)] if fail_init else [])
                + list(arguments)
            )
            return subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=check,
                timeout=600,
            )

        def database_value(statement: str) -> str:
            return compose(
                "exec",
                "-T",
                "db",
                "psql",
                "-U",
                "smoke",
                "-d",
                "smoke",
                "-Atc",
                statement,
            ).stdout.strip()

        try:
            print("Building pinned application images", flush=True)
            compose("build")
            print(
                "Checking that failed initialization blocks application startup",
                flush=True,
            )
            failed = compose("up", "-d", "api", "web", check=False, fail_init=True)
            if failed.returncode == 0:
                raise RuntimeError(
                    "Failed initialization unexpectedly started the stack"
                )
            running = compose(
                "ps", "--status", "running", "--services"
            ).stdout.splitlines()
            if "api" in running or "web" in running:
                raise RuntimeError("Application ran after initialization failed")
            compose("rm", "-sf", "initialize")
            print("Checking fresh initialization and all health probes", flush=True)
            compose("up", "--wait", "--wait-timeout", "120")
            wait_for_status(api_port, "/health", 200)
            wait_for_status(api_port, "/ready", 200)
            wait_for_status(web_port, "/", 200)
            for service in ("api", "web"):
                identity = compose("exec", "-T", service, "id", "-u").stdout.strip()
                if identity == "0":
                    raise RuntimeError("Application is running as root")
                container = compose("ps", "-q", service).stdout.strip()
                inspected = subprocess.run(
                    ["docker", "inspect", container],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=10,
                )
                host = json.loads(inspected.stdout)[0]["HostConfig"]
                if not host["ReadonlyRootfs"] or "ALL" not in host["CapDrop"]:
                    raise RuntimeError("Container isolation settings are missing")
            database_value(
                "INSERT INTO customer_accounts (name) VALUES ('Preserved smoke account')"
            )
            print("Checking recreation with an existing database volume", flush=True)
            compose("down")
            compose("up", "--wait", "--wait-timeout", "120")
            if (
                database_value(
                    "SELECT count(*) FROM customer_accounts WHERE name = 'Preserved smoke account'"
                )
                != "1"
            ):
                raise RuntimeError("Saved data was not preserved")
            print("Checking database outage and recovery", flush=True)
            login = {"email": "smoke@example.com", "password": "wrong smoke password"}
            if http_status(api_port, "/auth/login", login) != 401:
                raise RuntimeError("Database-backed authentication was unavailable")
            compose("stop", "db")
            wait_for_status(api_port, "/ready", 503)
            wait_for_status(api_port, "/health", 200)
            compose("start", "db")
            wait_for_status(api_port, "/ready", 200)
            if http_status(api_port, "/auth/login", login) != 401:
                raise RuntimeError(
                    "Application connections did not recover after restart"
                )
            print("Container smoke passed", flush=True)
        finally:
            compose("down", "--volumes", "--remove-orphans", check=False)
            subprocess.run(
                ["docker", "image", "rm", f"{project}-api", f"{project}-web"],
                capture_output=True,
                check=False,
                timeout=30,
            )


if __name__ == "__main__":
    main()
