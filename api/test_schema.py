"""The OpenAPI schema is complete and valid (#130).

Agents learn the game's API from this schema, so every operation must say
what it does in game terms. A new view without an @extend_schema summary
and description fails here — see api/README.md, Schema and docs.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from drf_spectacular.generators import SchemaGenerator

METHODS = {"get", "put", "post", "patch", "delete"}


@pytest.fixture(scope="module")
def schema():
    return SchemaGenerator().get_schema(request=None, public=True)


def operations(schema):
    for path, item in schema["paths"].items():
        for method, operation in item.items():
            if method in METHODS:
                yield f"{method.upper()} {path}", operation


def test_every_operation_has_a_summary_and_a_game_terms_description(schema):
    missing = [
        name for name, op in operations(schema)
        if not op.get("summary") or len(op.get("description", "")) < 40
    ]
    assert missing == []


def test_operation_ids_are_unique_and_explicit(schema):
    ids = [op["operationId"] for _, op in operations(schema)]
    assert len(ids) == len(set(ids))
    # Auto-generated ids look like "riders_retrieve"; ours are verbs.
    assert not [i for i in ids if i.endswith(("_retrieve", "_create", "_update"))]


def test_every_operation_accepts_a_bearer_token(schema):
    lacking = [
        name for name, op in operations(schema)
        if not any("bearerAuth" in s for s in op.get("security", []))
    ]
    assert lacking == []


def test_schema_generates_without_warnings(db):
    call_command(
        "spectacular", "--validate", "--fail-on-warn",
        stdout=StringIO(), stderr=StringIO(),
    )
