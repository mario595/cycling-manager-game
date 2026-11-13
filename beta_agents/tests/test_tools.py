import json

from beta_agents.game_api import GameAPI
from beta_agents.tools import Toolbox, operations_from_schema, truncate

from .conftest import FakeTransport


def test_session_operations_are_left_out(schema):
    names = {op.name for op in operations_from_schema(schema)}
    assert "login" not in names
    assert names == {"get_me", "set_squad", "get_roster", "fire_trainer", "report_a_problem"}


def test_path_and_body_become_arguments_with_refs_inlined(schema):
    ops = {op.name: op for op in operations_from_schema(schema)}
    params = ops["set_squad"].parameters
    assert set(params["properties"]) == {"race_id", "rider_ids", "leader_id"}  # readOnly dropped
    assert set(params["required"]) == {"race_id", "rider_ids", "leader_id"}
    assert params["properties"]["rider_ids"] == {"type": "array", "items": {"type": "integer"}}
    report = ops["report_a_problem"].parameters["properties"]["category"]
    assert report == {"type": "string", "enum": ["bug", "looks_wrong"], "description": "Kind."}
    assert ops["get_roster"].parameters["properties"]["page"]["description"] == "Page."
    tool = ops["get_me"].tool()
    assert tool["function"]["name"] == "get_me"
    assert "(GET /api/accounts/me/)" in tool["function"]["description"]


def test_execute_builds_the_request(schema):
    transport = FakeTransport({("PUT", "/api/racing/races/7/squad/"): (200, {"saved": True})})
    box = Toolbox(GameAPI("http://game", "k", transport=transport), operations_from_schema(schema))
    result = json.loads(box.execute("set_squad", {"race_id": 7, "rider_ids": [1, 2, 3, 4], "leader_id": 1}))
    assert result == {"status": 200, "body": {"saved": True}}
    method, url, headers, data = transport.requests[0]
    assert url == "http://game/api/racing/races/7/squad/"
    assert json.loads(data) == {"rider_ids": [1, 2, 3, 4], "leader_id": 1}
    assert headers["Authorization"] == "Bearer k"
    assert "Cookie" not in headers


def test_execute_errors_are_results(schema):
    transport = FakeTransport({("POST", "/api/staff/trainer/fire/"): (409, {"detail": "No trainer."})})
    box = Toolbox(GameAPI("http://game", "k", transport=transport), operations_from_schema(schema))
    assert json.loads(box.execute("fire_trainer", {})) == {"status": 409, "body": {"detail": "No trainer."}}
    assert json.loads(transport.requests[0][3]) == {}  # a POST always sends a body
    assert "no tool" in box.execute("nope", {})
    assert "Missing" in box.execute("set_squad", {"rider_ids": []})


def test_query_parameters(schema):
    transport = FakeTransport({("GET", "/api/riders/"): (200, [])})
    box = Toolbox(GameAPI("http://game", "k", transport=transport), operations_from_schema(schema))
    box.execute("get_roster", {"page": 2})
    assert transport.requests[0][1] == "http://game/api/riders/?page=2"


def test_truncate():
    assert truncate("abc", 5) == "abc"
    cut = truncate("x" * 20, 5)
    assert cut.startswith("xxxxx\n[... cut") and "20 characters" in cut


def test_simplify_handles_nullable_and_arrays():
    from beta_agents.tools import simplify

    assert simplify({"oneOf": [{"type": "null"}, {"type": "integer"}], "description": "d"}) == {"type": "integer", "description": "d"}
    assert simplify({"enum": ["a"]}) == {"enum": ["a"], "type": "string"}
    assert simplify("not a schema") == {}
