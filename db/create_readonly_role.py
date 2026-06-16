"""Create the SELECT-only DB role used by the agent at runtime.

Read-only "in depth": the defense lives at the connection layer, not just in the
prompt (spec.md §3, CLAUDE.md). This role can only SELECT on public tables.

Connects as the admin DATABASE_URL, creates/updates the role with the password
from ANALYST_RO_PASSWORD, grants SELECT, and prints the read-only connection
string to put in DATABASE_URL_RO.

Usage:
  uv run python db/create_readonly_role.py
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

import psycopg
from dotenv import load_dotenv
from psycopg import sql

RO_ROLE = "analyst_ro"


def _ro_connection_string(admin_url: str, password: str) -> str:
    """Derive the read-only pooler URL from the admin one.

    Supabase's session pooler expects the username as '<role>.<project-ref>'.
    The admin user is 'postgres.<ref>', so we swap 'postgres' for the RO role.
    """
    parts = urlsplit(admin_url)
    admin_user = parts.username or ""
    ref_suffix = admin_user.split(".", 1)[1] if "." in admin_user else ""
    ro_user = f"{RO_ROLE}.{ref_suffix}" if ref_suffix else RO_ROLE
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    netloc = f"{ro_user}:{password}@{host}{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def main() -> None:
    load_dotenv()
    admin_url = os.getenv("DATABASE_URL")
    password = os.getenv("ANALYST_RO_PASSWORD")
    if not admin_url:
        raise SystemExit("DATABASE_URL not set.")
    if not password:
        raise SystemExit("ANALYST_RO_PASSWORD not set in .env.")

    with psycopg.connect(admin_url) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            # Create role if missing, then (re)set its password idempotently.
            cur.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s", (RO_ROLE,)
            )
            exists = cur.fetchone() is not None
            if not exists:
                cur.execute(
                    sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD {}").format(
                        sql.Identifier(RO_ROLE), sql.Literal(password)
                    )
                )
                print(f"Created role {RO_ROLE}.")
            else:
                cur.execute(
                    sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                        sql.Identifier(RO_ROLE), sql.Literal(password)
                    )
                )
                print(f"Role {RO_ROLE} already existed; password reset.")

            # Minimal read-only grants on the public schema.
            cur.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(conn.info.dbname), sql.Identifier(RO_ROLE)
                )
            )
            cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(RO_ROLE)))
            cur.execute(
                sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(
                    sql.Identifier(RO_ROLE)
                )
            )
            # Cover tables created in the future too.
            cur.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {}"
                ).format(sql.Identifier(RO_ROLE))
            )
            # Explicitly ensure NO write privileges leaked in.
            cur.execute(
                sql.SQL(
                    "REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM {}"
                ).format(sql.Identifier(RO_ROLE))
            )

    print("\nRead-only role ready. Put this in .env as DATABASE_URL_RO:\n")
    print(_ro_connection_string(admin_url, password))


if __name__ == "__main__":
    main()
