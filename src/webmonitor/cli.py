"""Process entry point: server command plus administrative and token commands."""
import argparse
import asyncio
import getpass
import sys
from uuid import UUID


def _parse_scopes(raw: str | None, *, allow_approve: bool) -> list[str]:
    from webmonitor.services.tokens import ALL_SCOPES, DEFAULT_SCOPES

    if raw is None:
        scopes = set(DEFAULT_SCOPES)
    elif raw.strip().lower() == "all":
        scopes = set(ALL_SCOPES)
    else:
        scopes = {item.strip() for item in raw.split(",") if item.strip()}
    if allow_approve:
        scopes.add("drafts:approve")
    return sorted(scopes)


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
    token_create = commands.add_parser("token-create", help="Create a personal access token for MCP clients")
    token_create.add_argument("--email", required=True)
    token_create.add_argument("--name", required=True)
    token_create.add_argument("--scopes", default=None,
                              help="Comma-separated scopes or 'all' (default excludes drafts:approve)")
    token_create.add_argument("--allow-approve", action="store_true",
                              help="Include drafts:approve in the token scopes")
    token_create.add_argument("--ttl-days", type=int, default=90,
                              help="Token lifetime in days, or 0 for no expiration")
    token_list = commands.add_parser("token-list", help="List personal access tokens for a user")
    token_list.add_argument("--email", required=True)
    token_revoke = commands.add_parser("token-revoke", help="Revoke a personal access token by ID")
    token_revoke.add_argument("--id", required=True)
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
    from webmonitor.services.tokens import cli_create_token, cli_list_tokens, cli_revoke_token

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
                elif args.command == "invite-create":
                    print(await invite_create(session, email=args.email, ttl_hours=args.ttl_hours))
                elif args.command == "token-create":
                    ttl_days = None if args.ttl_days == 0 else args.ttl_days
                    scopes = _parse_scopes(args.scopes, allow_approve=args.allow_approve)
                    row, raw = await cli_create_token(
                        session, email=args.email, name=args.name,
                        scopes=scopes, ttl_days=ttl_days,
                    )
                    print(raw)
                    print(
                        f"id={row.id} prefix={row.token_prefix} scopes={','.join(row.scopes)}",
                        file=sys.stderr,
                    )
                elif args.command == "token-list":
                    items = await cli_list_tokens(session, email=args.email)
                    for item in items:
                        state = "revoked" if item.revoked_at else "active"
                        print(f"{item.id}  {item.token_prefix}  {state}  {item.name}  [{','.join(item.scopes)}]")
                elif args.command == "token-revoke":
                    row = await cli_revoke_token(session, token_id=UUID(args.id))
                    print(f"Revoked {row.id}")
        finally:
            await get_engine().dispose()

    try:
        asyncio.run(execute())
    except DomainError as exc:
        print(exc.code, file=sys.stderr)
        raise SystemExit(1) from None
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
