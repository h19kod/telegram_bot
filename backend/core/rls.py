"""PostgreSQL row-level security: defence in depth behind ``for_business()``.

Once a request is bound to a business (``set_business_context``) its connection switches to the
restricted role ``app_tenant`` with ``app.business_id`` set. That role has DML rights only and a
policy on every table with a ``business_id`` column, so a query that forgets ``for_business()``
still cannot read or write another tenant's rows (no setting → no rows: fails closed).
Migrations, Celery tasks and platform-console requests keep the owner role and are unaffected.

Policies are (re)applied after every ``migrate`` (post_migrate), so new tenant tables are covered.
"""

from __future__ import annotations

from typing import Any

from django.db import DatabaseError, connection

ROLE = "app_tenant"
SETTING = "app.business_id"
POLICY = "tenant_isolation"
_ACTIVE = "_sop_rls_active"
_PREDICATE = f"business_id = nullif(current_setting('{SETTING}', true), '')::uuid"


def activate(business_id: object) -> None:
    with connection.cursor() as cur:
        cur.execute("SELECT set_config(%s, %s, false)", [SETTING, str(business_id)])
        cur.execute(f"SET ROLE {ROLE}")
    setattr(connection, _ACTIVE, True)


def deactivate() -> None:
    if not getattr(connection, _ACTIVE, False):
        return
    setattr(connection, _ACTIVE, False)
    try:
        with connection.cursor() as cur:
            cur.execute("RESET ROLE")
            cur.execute("SELECT set_config(%s, '', false)", [SETTING])
    except DatabaseError:
        # e.g. an aborted transaction: never hand a restricted session to the next request.
        connection.close()


def reset_pooled_connection(conn: Any) -> None:
    """psycopg pool ``reset`` hook: a returned connection never keeps the tenant role."""
    conn.execute("RESET ROLE")
    conn.execute(f"SELECT set_config('{SETTING}', '', false)")
    conn.commit()


def tenant_tables(cursor: Any) -> list[str]:
    cursor.execute(
        """
        SELECT c.table_name FROM information_schema.columns c
        JOIN information_schema.tables t USING (table_schema, table_name)
        WHERE c.table_schema = current_schema() AND c.column_name = 'business_id'
          AND t.table_type = 'BASE TABLE'
        ORDER BY 1
        """
    )
    return [r[0] for r in cursor.fetchall()]


def apply_policies(**_: Any) -> None:
    with connection.cursor() as cur:
        cur.execute(
            f"""
            DO $$ BEGIN
              CREATE ROLE {ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS;
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$
            """
        )
        cur.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        if not cur.fetchone()[0]:
            cur.execute(f"GRANT {ROLE} TO current_user")
        cur.execute(f"GRANT USAGE ON SCHEMA public TO {ROLE}")
        cur.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {ROLE}"
        )
        cur.execute(f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO {ROLE}")
        for table in tenant_tables(cur):
            t = connection.ops.quote_name(table)
            cur.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
            cur.execute(f"DROP POLICY IF EXISTS {POLICY} ON {t}")
            cur.execute(
                f"CREATE POLICY {POLICY} ON {t} TO {ROLE} "
                f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
            )
