import pytest

from beta_agents.game_api import Response

SCHEMA = {
    "openapi": "3.0.3",
    "paths": {
        "/api/accounts/login/": {"post": {"operationId": "login", "summary": "Log in"}},
        "/api/accounts/me/": {"get": {"operationId": "get_me", "summary": "Who you are", "description": "Your team."}},
        "/api/racing/races/{race_id}/squad/": {
            "parameters": [],
            "put": {
                "operationId": "set_squad",
                "summary": "Pick your squad",
                "parameters": [{"in": "path", "name": "race_id", "required": True, "schema": {"type": "integer"}}],
                "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Squad"}}}},
            },
        },
        "/api/riders/": {
            "get": {
                "operationId": "get_roster",
                "summary": "Your roster",
                "parameters": [{"in": "query", "name": "page", "schema": {"type": "integer"}, "description": "Page."}],
            }
        },
        "/api/staff/trainer/fire/": {"post": {"operationId": "fire_trainer", "summary": "Fire"}},
        "/api/feedback/reports/": {
            "post": {
                "operationId": "report_a_problem",
                "summary": "Report a problem",
                "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Report"}}}},
            }
        },
    },
    "components": {
        "schemas": {
            "Squad": {
                "type": "object",
                "properties": {
                    "rider_ids": {"type": "array", "items": {"type": "integer"}},
                    "leader_id": {"type": "integer"},
                    "saved": {"type": "boolean", "readOnly": True},
                },
                "required": ["rider_ids", "leader_id", "saved"],
            },
            "Category": {"enum": ["bug", "looks_wrong"], "type": "string"},
            "Report": {
                "type": "object",
                "properties": {
                    "category": {"allOf": [{"$ref": "#/components/schemas/Category"}], "description": "Kind."},
                    "text": {"type": "string", "maxLength": 4000},
                },
                "required": ["category", "text"],
            },
        }
    },
}


class FakeTransport:
    """Records requests and answers from a {(method, path): (status, body)} map."""

    def __init__(self, routes=None):
        self.routes = dict(routes or {})
        self.requests = []

    def __call__(self, method, url, headers, data, timeout):
        self.requests.append((method, url, headers, data))
        path = url.split("://", 1)[1].split("/", 1)[1]
        path = "/" + path.split("?", 1)[0]
        answer = self.routes.get((method, path), (404, {"detail": "not found"}))
        if callable(answer):
            answer = answer()
        status, body = answer
        return Response(status=status, body=body, headers={})


@pytest.fixture
def schema():
    return SCHEMA
