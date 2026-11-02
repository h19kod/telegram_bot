"""PostgreSQL row-level security: the database itself hides other tenants' rows (defence in depth)."""

import pytest
from django.db import DatabaseError, connection, transaction

from apps.products.models import Product
from core import rls
from core.middleware import set_business_context
from tests.factories import make_business, make_product
from tests.helpers import auth

pytestmark = pytest.mark.django_db


def current_role():
    with connection.cursor() as cur:
        cur.execute("SELECT current_user, current_setting('app.business_id', true)")
        return cur.fetchone()


@pytest.fixture
def two_tenants():
    a, b = make_business(), make_business()
    pa, pb = make_product(a), make_product(b)
    yield a, b, pa, pb
    rls.deactivate()


def test_every_tenant_table_has_a_policy():
    with connection.cursor() as cur:
        tables = set(rls.tenant_tables(cur))
        cur.execute(
            "SELECT tablename FROM pg_policies WHERE policyname = %s AND %s = ANY(roles::text[])",
            [rls.POLICY, rls.ROLE],
        )
        covered = {r[0] for r in cur.fetchall()}
        cur.execute(
            "SELECT relname FROM pg_class WHERE relrowsecurity AND relname = ANY(%s)",
            [list(tables)],
        )
        enabled = {r[0] for r in cur.fetchall()}
    assert len(tables) > 30
    assert tables == covered == enabled


def test_unscoped_query_only_sees_current_tenant(two_tenants):
    a, _b, pa, pb = two_tenants
    set_business_context(a.id)
    ids = set(Product.objects.values_list("id", flat=True))  # no for_business() on purpose
    assert pa.id in ids
    assert pb.id not in ids
    assert not Product.objects.filter(id=pb.id).exists()


def test_cannot_write_into_another_tenant(two_tenants):
    a, b, pa, pb = two_tenants
    set_business_context(a.id)
    assert Product.objects.filter(id=pb.id).update(price=1) == 0
    pa.business_id = b.id
    with pytest.raises(DatabaseError), transaction.atomic():
        pa.save(update_fields=["business"])


def test_tenant_role_without_business_sees_nothing(two_tenants):
    with connection.cursor() as cur:
        cur.execute(f"SET ROLE {rls.ROLE}")
        try:
            assert Product.objects.count() == 0
        finally:
            cur.execute("RESET ROLE")


def test_deactivate_restores_owner_role(two_tenants):
    a, *_ = two_tenants
    owner = current_role()[0]
    set_business_context(a.id)
    assert current_role() == (rls.ROLE, str(a.id))
    rls.deactivate()
    assert current_role() == (owner, "")
    assert Product.objects.count() == 2


def test_request_resets_role_afterwards(api, two_tenants):
    a, *_ = two_tenants
    owner = current_role()[0]
    r = auth(api, a.owner).get(f"/api/v1/b/{a.id}/products")
    assert r.status_code == 200
    assert r.json()["count"] == 1
    assert current_role() == (owner, "")


def test_rls_blocks_a_view_that_forgets_for_business(api, two_tenants, monkeypatch):
    from core.tenancy import TenantViewSet

    a, _b, pa, pb = two_tenants
    # Simulate the bug RLS exists for: a view querying the whole table.
    monkeypatch.setattr(TenantViewSet, "base_queryset", lambda self: self.model.objects.all())
    client = auth(api, a.owner)
    assert client.get(f"/api/v1/b/{a.id}/products/{pb.id}").status_code == 404
    listed = {p["id"] for p in client.get(f"/api/v1/b/{a.id}/products").json()["results"]}
    assert listed == {str(pa.id)}
