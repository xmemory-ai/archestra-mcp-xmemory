"""Validate the Archestra catalogue manifests in this directory.

Three checks, in order of authority:

1. JSON Schema validation of both manifests against the *live* MCP Catalog API's OpenAPI spec
   (``https://archestra.ai/mcp-catalog/api/docs``, component ``ArchestraMcpServerManifest``) —
   the same contract Archestra's own codegen consumes, so it cannot drift from their pipeline.
2. Tool-list consistency: the ``xmemory`` manifest must list exactly the default-on instance tools
   declared in ``api/instance_tool_catalog.py`` (the single source of truth for the instance
   connection), and the admin manifest exactly the ``ADMIN_ONLY_TOOLS`` set in ``api/xmcp/server.py``.
   Read textually so this script stays dependency-free of the api package.
3. Description consistency against ``api/describe.py`` (the canonical agent-facing tool docs):
   the FIRST_PARTY_POSITIONING paragraph must appear verbatim in the main manifest's description,
   the admin manifest must state its instance-management-only scope, and each manifest tool that has
   a canonical ``*_DESCRIPTION`` must share distinctive vocabulary with that canon's headline
   sentence — a tripwire for one-liners drifting from what the server actually tells agents.
4. Liveness of the URLs the manifests point reviewers at (server, docs, OAuth discovery).

Run from the repo root:

    uv run --no-project --with jsonschema python integrations/archestra/validate.py

Exit code 0 = all checks passed. Network access to archestra.ai and mcp.xmemory.ai is required.
Checks 2 and 3 need the xmemory monorepo sources (``api/``); when this directory is used standalone
(e.g. a public mirror), those checks are skipped with a notice and the rest still run.
"""

import ast
import copy
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import jsonschema

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
OPENAPI_URL = "https://archestra.ai/mcp-catalog/api/docs"
MANIFESTS = ("xmemory.manifest.json", "xmemory-admin.manifest.json")

# Manifest tool -> canonical description constant in api/describe.py. Tools absent here (the
# suggestion lifecycle, admin listing/getters) have no describe.py canon and are skipped.
DESCRIBE_CANON = {
    "write": "WRITE_DESCRIPTION",
    "write_async": "WRITE_ASYNC_DESCRIPTION",
    "write_status": "WRITE_STATUS_DESCRIPTION",
    "read": "READ_DESCRIPTION",
    "get_instance_schema": "GET_SCHEMA_DESCRIPTION",
    "get_instance_id": "GET_INSTANCE_ID_DESCRIPTION",
    "admin_generate_schema": "GENERATE_SCHEMA_DESCRIPTION",
    "admin_delete_instance": "DELETE_INSTANCE_DESCRIPTION",
    "admin_delete_instance_by_id": "DELETE_INSTANCE_DESCRIPTION",
    "admin_update_instance_metadata": "UPDATE_METADATA_DESCRIPTION",
    "admin_update_instance_metadata_by_id": "UPDATE_METADATA_DESCRIPTION",
    "admin_patch_instance_metadata": "UPDATE_METADATA_DESCRIPTION",
    "admin_patch_instance_metadata_by_id": "UPDATE_METADATA_DESCRIPTION",
}


def fetch_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.load(resp)


def build_manifest_schema(spec: dict[str, Any]) -> dict[str, Any]:
    """Convert the OpenAPI component into a self-contained JSON Schema document."""

    def rewrite(node: Any) -> None:
        if isinstance(node, dict):
            if "$ref" in node:
                node["$ref"] = node["$ref"].replace("#/components/schemas/", "#/$defs/")
            # OpenAPI 3.0 expresses optional-null via ``nullable``; JSON Schema needs a type union.
            if node.pop("nullable", False):
                if "type" in node:
                    node["type"] = [node["type"], "null"]
                elif "$ref" in node:
                    node["anyOf"] = [{"$ref": node.pop("$ref")}, {"type": "null"}]
            for value in node.values():
                rewrite(value)
        elif isinstance(node, list):
            for value in node:
                rewrite(value)

    defs = copy.deepcopy(spec["components"]["schemas"])
    rewrite(defs)
    return {"$defs": defs, "$ref": "#/$defs/ArchestraMcpServerManifest"}


def expected_instance_tools() -> set[str]:
    """Default-on tools from api/instance_tool_catalog.py — specs without ``default_on=False``.

    Tool labels may themselves contain parentheses, so a lazy ``\\(.*?\\)`` regex under-captures.
    Segmenting the catalog literal between ``InstanceToolSpec(`` occurrences keeps each spec whole.
    """
    text = (REPO_ROOT / "api" / "instance_tool_catalog.py").read_text()
    tools: set[str] = set()
    for segment in text.split("InstanceToolSpec(")[1:]:
        segment = segment.split("\n]")[0]
        name = re.search(r'name="(\w+)"', segment)
        if name and "default_on=False" not in segment:
            tools.add(name.group(1))
    return tools


def expected_admin_tools() -> set[str]:
    """The ADMIN_ONLY_TOOLS frozenset literal in api/xmcp/server.py."""
    text = (REPO_ROOT / "api" / "xmcp" / "server.py").read_text()
    match = re.search(r"ADMIN_ONLY_TOOLS:\s*frozenset\[str\]\s*=\s*frozenset\((.*?)\)\n", text, re.DOTALL)
    if not match:
        raise ValueError("ADMIN_ONLY_TOOLS literal not found in api/xmcp/server.py")
    return set(re.findall(r'"(admin_\w+)"', match.group(1)))


def describe_constants() -> dict[str, str]:
    """String constants from api/describe.py, read via ``ast`` (adjacent literals merge at parse time)."""
    tree = ast.parse((REPO_ROOT / "api" / "describe.py").read_text())
    constants: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                value = ast.literal_eval(node.value)
            except ValueError:
                continue
            if isinstance(value, str):
                constants[node.targets[0].id] = value
    return constants


def stems(text: str) -> set[str]:
    """Crude stems of the distinctive words in ``text`` — tolerant of inflection (sync/synchronously)."""
    return {word[:6] for word in re.findall(r"[a-z]+", text.lower()) if len(word) > 3 and word != "xmemory"}


def check_descriptions(manifests: dict[str, dict[str, Any]], failures: list[str]) -> None:
    canon = describe_constants()

    positioning = " ".join(canon["FIRST_PARTY_POSITIONING"].split())
    main_description = " ".join(manifests["xmemory.manifest.json"]["description"].split())
    positioning_ok = positioning in main_description
    if not positioning_ok:
        failures.append("xmemory.manifest.json: description must contain FIRST_PARTY_POSITIONING verbatim")
    print(f"[descr]  first-party positioning: {'OK' if positioning_ok else 'MISSING'}")

    admin_description = manifests["xmemory-admin.manifest.json"]["description"].lower()
    admin_scope_ok = "cannot read or write" in admin_description
    if not admin_scope_ok:
        failures.append("xmemory-admin.manifest.json: description must state admin cannot read or write instance data")
    print(f"[descr]  admin management-only scope: {'OK' if admin_scope_ok else 'MISSING'}")

    for name, manifest in manifests.items():
        for tool in manifest["tools"]:
            constant = DESCRIBE_CANON.get(tool["name"])
            if constant is None:
                continue
            headline = re.split(r"(?<=[.!?])\s", canon[constant].split("\n\n")[0])[0]
            overlap = stems(tool["description"]) & stems(headline)
            if len(overlap) < 2:
                failures.append(
                    f"{name}: tool '{tool['name']}' description drifted from describe.py {constant} "
                    f"headline ({headline!r}); shared stems: {sorted(overlap)}"
                )
    drifted = [f for f in failures if "drifted from describe.py" in f]
    print(f"[descr]  tool one-liners vs describe.py canon: {'OK' if not drifted else f'{len(drifted)} drifted'}")


def check_url(url: str) -> bool:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            return resp.status < 400
    except urllib.error.HTTPError as err:
        # The MCP endpoint itself answers 4xx to plain unauthenticated GETs; that still proves liveness.
        return err.code in (400, 401, 405, 406)


def main() -> int:
    failures: list[str] = []

    schema = build_manifest_schema(fetch_json(OPENAPI_URL))
    validator = jsonschema.Draft202012Validator(schema)
    manifests = {name: json.loads((HERE / name).read_text()) for name in MANIFESTS}

    for name, doc in manifests.items():
        errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
        for error in errors:
            failures.append(f"{name}: {'/'.join(map(str, error.path)) or '<root>'} — {error.message}")
        print(f"[schema] {name}: {'OK' if not errors else f'{len(errors)} error(s)'}")

    tool_sources = (REPO_ROOT / "api" / "instance_tool_catalog.py", REPO_ROOT / "api" / "xmcp" / "server.py")
    if all(path.is_file() for path in tool_sources):
        expectations = {
            "xmemory.manifest.json": expected_instance_tools(),
            "xmemory-admin.manifest.json": expected_admin_tools(),
        }
        for name, expected in expectations.items():
            actual = {tool["name"] for tool in manifests[name]["tools"]}
            if actual != expected:
                missing, extra = expected - actual, actual - expected
                failures.append(f"{name}: tools drift — missing {sorted(missing)}, extra {sorted(extra)}")
            print(f"[tools]  {name}: {'OK' if actual == expected else 'DRIFT'} ({len(actual)} tools)")
    else:
        print("[tools]  SKIPPED — xmemory monorepo sources not found (running standalone)")

    if (REPO_ROOT / "api" / "describe.py").is_file():
        check_descriptions(manifests, failures)
    else:
        print("[descr]  SKIPPED — api/describe.py not found (running standalone)")

    urls = {manifests[name]["server"]["url"] for name in MANIFESTS}
    urls |= {manifests[name]["server"]["docs_url"] for name in MANIFESTS}
    urls.add("https://mcp.xmemory.ai/.well-known/oauth-protected-resource")
    for url in sorted(urls):
        alive = check_url(url)
        if not alive:
            failures.append(f"URL not reachable: {url}")
        print(f"[url]    {url}: {'OK' if alive else 'UNREACHABLE'}")

    if failures:
        print("\nFAILED:")
        for failure in failures:
            print(" -", failure)
        return 1
    print("\nAll manifest checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
