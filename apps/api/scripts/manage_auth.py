"""Provision the first admin or recover a password through trusted local access."""

import argparse
import asyncio
import getpass
import os

from pydantic import ValidationError
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.identity.admin import bootstrap_admin, reset_password
from api.identity.schemas import LocalAccountInput


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("create-admin", "reset-password"))
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="Administrator")
    parser.add_argument("--last-name", default="ResolveFlow")
    args = parser.parse_args()
    raw_url = os.getenv("DATABASE_URL")
    if not raw_url:
        parser.error("DATABASE_URL is required")
    password = getpass.getpass("Password (15-128 characters): ")
    if getpass.getpass("Confirm password: ") != password:
        parser.error("Passwords do not match")
    try:
        validated = LocalAccountInput.model_validate(
            {
                "email": args.email,
                "name": args.name,
                "last_name": args.last_name,
                "password": password,
            }
        )
        email = str(validated.email)
    except ValidationError:
        parser.error(
            "Use a valid email, non-empty names, and a 15-128 character password"
        )
    engine = create_async_engine(make_url(raw_url).set(drivername="postgresql+psycopg"))
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            if args.command == "create-admin":
                user = await bootstrap_admin(
                    session, email, validated.name, validated.last_name, password
                )
                print(
                    f"Created administrator {user.id}; no customer account grants assigned."
                )
            else:
                await reset_password(session, email, password)
                print(
                    "Password updated and existing sessions revoked. Disabled access remains disabled."
                )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
