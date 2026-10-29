"""Dev/test command dispatch; pytest always gets a newly created disposable database."""
import asyncio
import os
import secrets
import subprocess
import sys
from uuid import uuid4

import asyncpg
from sqlalchemy.engine import URL


async def tests(arguments):
    database = "wm_test_" + uuid4().hex
    username = os.environ.get("PGUSER", "webmonitor")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    host = os.environ.get("PGHOST", "postgres")
    port = int(os.environ.get("PGPORT", "5432"))
    admin = await asyncpg.connect(host=host, port=port, user=username,
                                  password=password, database="postgres", timeout=15)
    created = False
    try:
        await admin.execute(f'CREATE DATABASE "{database}"')
        created = True
        environment = dict(os.environ)
        environment.update(PGDATABASE=database, PGUSER=username, PGPASSWORD=password,
                           DEVELOPMENT_MODE="true",
                           SECRET_KEY=secrets.token_urlsafe(48))
        environment["TEST_DATABASE_URL"] = URL.create(
            "postgresql+asyncpg", username=username, password=password,
            host=host, port=port, database=database).render_as_string(hide_password=False)
        initialization = subprocess.run([sys.executable, "-c",
            "import asyncio; from webmonitor.db import initialize_database; "
            "asyncio.run(initialize_database())"], env=environment)
        if initialization.returncode:
            return initialization.returncode
        return subprocess.run([sys.executable, "-m", "pytest", *arguments], env=environment).returncode
    finally:
        if created:
            # Only the random name created in this invocation is ever dropped.
            await admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                                "WHERE datname = $1 AND pid <> pg_backend_pid()", database)
            await admin.execute(f'DROP DATABASE "{database}"')
        await admin.close()


def main():
    arguments = sys.argv[1:] or ["python"]
    if arguments[0] == "pytest":
        try:
            result = asyncio.run(tests(arguments[1:]))
        except Exception:
            # Connection exceptions can contain credentials; never print their repr.
            print("Isolated test database bootstrap/cleanup failed; check the PostgreSQL service.",
                  file=sys.stderr)
            result = 1
        raise SystemExit(result)
    os.execvp(arguments[0], arguments)


if __name__ == "__main__":
    main()
