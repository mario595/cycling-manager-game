"""The game's API operations as model tools, generated from the live OpenAPI
schema (#130), so a new endpoint becomes a tool without touching the harness.

Each operation becomes one function tool named by its `operationId`. Its path
parameters, query parameters and request-body fields become the tool's
top-level arguments. The tool's description is the operation's own summary
and description, which are written in game terms.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .game_api import GameAPI

# Session plumbing a token client never needs, and a large binary replay the
# results endpoint already summarises (plan, decision 4).
EXCLUDED_OPERATIONS = frozenset({"login", "logout", "register", "get_race_log"})

# What a model is given of a JSON Schema: enough to call correctly, nothing a
# provider's validator might choke on.
_KEPT_KEYS = ("type", "description", "enum", "format", "minimum", "maximum", "minLength", "maxLength", "default")

MAX_RESULT_CHARS = 8000


@dataclass
class Operation:
    name: str
    method: str
    path: str
    description: str
    path_params: list[str] = field(default_factory=list)
    query_params: list[str] = field(default_factory=list)
    body_fields: list[str] = field(default_factory=list)
    body_is_object: bool = True
    parameters: dict = field(default_factory=dict)  # the tool's JSON Schema

    def tool(self) -> dict:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


def resolve(node: Any, schema: dict, depth: int = 0) -> Any:
    """Inline every `$ref`, so each tool's schema stands on its own."""
    if depth > 12:
        return {}
    if isinstance(node, dict):
        if "$ref" in node:
            target: Any = schema
            for part in node["$ref"].lstrip("#/").split("/"):
                target = target[part]
            return resolve(target, schema, depth + 1)
        return {key: resolve(value, schema, depth + 1) for key, value in node.items()}
    if isinstance(node, list):
        return [resolve(item, schema, depth + 1) for item in node]
    return node


def simplify(node: dict) -> dict:
    """Trim a resolved schema to the subset model providers all accept."""
    if not isinstance(node, dict):
        return {}
    for combinator in ("allOf", "oneOf", "anyOf"):
        if combinator in node:
            # drf-spectacular wraps enums and nullables this way. Take the
            # first branch that says something, keeping the description.
            branches = [b for b in node[combinator] if isinstance(b, dict) and b.get("type") != "null"]
            merged = dict(branches[0]) if branches else {}
            if "description" in node:
                merged.setdefault("description", node["description"])
            return simplify(merged)
    out = {key: node[key] for key in _KEPT_KEYS if key in node}
    if node.get("type") == "object" or "properties" in node:
        out["type"] = "object"
        properties = {
            name: simplify(prop)
            for name, prop in node.get("properties", {}).items()
            if not (isinstance(prop, dict) and prop.get("readOnly"))
        }
        out["properties"] = properties
        required = [name for name in node.get("required", []) if name in properties]
        if required:
            out["required"] = required
    if node.get("type") == "array":
        out["items"] = simplify(node.get("items", {}))
    if "type" not in out and "enum" in out:
        out["type"] = "string"
    return out


def operations_from_schema(schema: dict) -> list[Operation]:
    operations = []
    for path, methods in sorted(schema.get("paths", {}).items()):
        for method, raw in methods.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            name = raw.get("operationId")
            if not name or name in EXCLUDED_OPERATIONS:
                continue
            op = resolve(raw, schema)
            properties: dict[str, dict] = {}
            required: list[str] = []
            operation = Operation(
                name=name,
                method=method.upper(),
                path=path,
                description=_describe(op, method, path),
            )
            for param in op.get("parameters", []):
                if param.get("in") not in {"path", "query"}:
                    continue
                prop = simplify(param.get("schema", {}))
                if param.get("description"):
                    prop["description"] = param["description"]
                properties[param["name"]] = prop
                if param["in"] == "path":
                    operation.path_params.append(param["name"])
                    required.append(param["name"])
                else:
                    operation.query_params.append(param["name"])
                    if param.get("required"):
                        required.append(param["name"])
            body = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
            if body:
                body = simplify(body)
                if body.get("type") == "object":
                    for field_name, prop in body.get("properties", {}).items():
                        properties[field_name] = prop
                        operation.body_fields.append(field_name)
                    required.extend(body.get("required", []))
                else:
                    operation.body_is_object = False
                    properties["body"] = body
                    operation.body_fields.append("body")
                    required.append("body")
            operation.parameters = {"type": "object", "properties": properties}
            if required:
                operation.parameters["required"] = required
            operations.append(operation)
    return operations


def _describe(op: dict, method: str, path: str) -> str:
    summary = op.get("summary", "")
    description = op.get("description", "")
    text = f"{summary}. {description}".strip(" .") + f" ({method.upper()} {path})"
    return text[:1024]


class Toolbox:
    """The tools for one visit, and how to run them against the game."""

    def __init__(self, api: GameAPI, operations: list[Operation]):
        self.api = api
        self.operations = {op.name: op for op in operations}

    def tools(self) -> list[dict]:
        return [op.tool() for op in self.operations.values()]

    def execute(self, name: str, arguments: dict) -> str:
        """Call one operation. Always returns text for the model: an HTTP
        error is a result to read, not an exception."""
        operation = self.operations.get(name)
        if operation is None:
            return json.dumps({"error": f"There is no tool called {name!r}."})
        try:
            path = operation.path
            for param in operation.path_params:
                if param not in arguments:
                    return json.dumps({"error": f"Missing required argument {param!r}."})
                path = path.replace("{" + param + "}", str(arguments[param]))
            query = {p: arguments[p] for p in operation.query_params if p in arguments} or None
            body = None
            if operation.body_fields:
                if operation.body_is_object:
                    body = {f: arguments[f] for f in operation.body_fields if f in arguments}
                else:
                    body = arguments.get("body")
            elif operation.method in {"POST", "PUT", "PATCH"}:
                body = {}
            response = self.api.call(operation.method, path, body=body, query=query)
        except (TypeError, ValueError) as error:
            return json.dumps({"error": f"Bad arguments: {error}"})
        return truncate(json.dumps({"status": response.status, "body": response.body}, ensure_ascii=False))


def truncate(text: str, limit: int = MAX_RESULT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[... cut: the full response was {len(text)} characters. Ask for something narrower, such as one rider or one race.]"
