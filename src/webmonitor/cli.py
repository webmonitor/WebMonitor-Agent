"""Process entry point: one server command plus two administrative commands."""
import argparse
import asyncio
import getpass
import sys


def main() -> None:
    parser = argparse.ArgumentParser(prog="webmonitor")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Run the API and every background loop")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", default=8000, type=int)
    admin = commands.add_parser("admin-create", help="Create an administrator with an interactive password")
    admin.add_argument("--email", required=True)
    invite = commands.add_parser("invite-create", help="Issue an allowlisted single-use invitation")
    invite.add_argument("--email", required=True)
    invite.add_argument("--ttl-hours", type=int, default=24)
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn

        from webmonitor.config import get_settings
        trusted_proxy = get_settings().trusted_proxy_ip
        uvicorn.run("webmonitor.api.app:create_app", factory=True, host=args.host,
                    port=args.port, proxy_headers=trusted_proxy is not None,
                    forwarded_allow_ips=trusted_proxy or "", access_log=False)
        return
    from webmonitor.db import get_engine, get_session_factory
    from webmonitor.errors import DomainError
    from webmonitor.services.accounts import admin_create, invite_create

    password = None
    if args.command == "admin-create":
        password = getpass.getpass("Password (12–128 characters): ")
        if password != getpass.getpass("Confirm password: "):
            parser.error("Passwords do not match")

    async def execute():
        try:
            async with get_session_factory()() as session:
                if args.command == "admin-create":
                    await admin_create(session, email=args.email, password=password)
                    print("Administrator created")
                else:
                    print(await invite_create(session, email=args.email, ttl_hours=args.ttl_hours))
        finally:
            await get_engine().dispose()

    try:
        asyncio.run(execute())
    except DomainError as exc:
        print(exc.code, file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
