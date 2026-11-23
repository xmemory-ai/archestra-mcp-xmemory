# xmemory — Archestra MCP Catalog listing

Manifests for the **Archestra MCP Catalog** (`https://archestra.ai/mcp-catalog`), plus the recipe
for registering xmemory in an **Archestra platform** deployment's private MCP registry. This is a
thin pointer to the xmemory remote MCP server — no backend code. (Public mirror; the source of
truth lives in the xmemory monorepo.)

> **First-party positioning.** xmemory is a first-party memory store: it holds the data you
> explicitly save to your xmemory instance, in xmemory's own backend. It does **not** read the
> model's built-in memory, your past chat history, or your files, email, or cloud drives — it
> only stores and returns what is written to this instance.

## What xmemory is

xmemory is a general-purpose **memory engine for agentic AI systems**. Agents keep a
natural-language read/write interface while xmemory handles extraction, validation, deduplication,
stateful updates, relations, provenance, and schema evolution. Schema is a control dial, not an
adoption barrier: an instance can begin with a loose, EAV-like schema that captures facts flexibly,
then move toward typed, normalized structures as the workflow matures — xmemory generates a useful
starting schema from a workflow description and evolves it from observed read/write traffic.

On xmemory's four-domain end-to-end memory benchmark (updates, deletions, relation changes,
aggregation, negative/exclusion cases), xmemory reports 99.15% precision / 95.12% recall / 97.10%
F1 versus 80.16–87.24% F1 for compared systems — results on that published benchmark, not a
universal guarantee. Architecture and benchmarks: the [white paper](https://arxiv.org/abs/2604.27906);
product docs: [xmemory.ai](https://xmemory.ai), LLM-ready context: [llms.txt](https://xmemory.ai/llms.txt).

The MCP server is **remote (Streamable HTTP)** at `https://mcp.xmemory.ai` — nothing to install or
run. The `read`, `write` and `write_async` descriptions name the bound instance in their first
line and carry its purpose and object types at the end. The server `instructions` say the same,
but several clients drop that field — so the bound instance's *name* is what reaches every client,
while the purpose and object types reach only clients that do not truncate tool descriptions.
Call `get_instance_schema` for the full schema. Full MCP guide: **https://xmemory.ai/mcp**.

## What Archestra is

[Archestra](https://archestra.ai) is an open-source, self-hosted enterprise AI platform
(`github.com/archestra-ai/archestra`) with two catalog surfaces, and this directory serves both:

1. **Public MCP Catalog** — `archestra.ai/mcp-catalog`, a hand-maintained directory of MCP servers
   served from `archestra.ai/mcp-catalog/api` and built from `mcp-catalog/data/` in
   `github.com/archestra-ai/archestra`. Entries are `ArchestraMcpServerManifest` JSON documents;
   the platform's registry picker shows only entries with `archestra_config.works_in_archestra: true`.
   The catalog lists the data plane as `xmemory__remote-mcp`. It names remote entries after the
   hostname alone, so the admin connection (same host, `/admin`) cannot get an entry of its own;
   register it through the private registry instead.
2. **Private MCP Registry** — inside each Archestra platform deployment; org admins register
   servers at runtime (UI `/mcp/registry` or `POST /api/internal_mcp_catalog`). Works today with
   no public listing needed — see the recipes below.

## Two connections

The listing registers **two** servers; connect and authorize them **separately** depending on what
you need (same split as our Cursor and Claude Code listings):

- **`xmemory`** — the **memory / data plane**. Root URL `https://mcp.xmemory.ai`; on sign-in you
  choose the instance to read and write.
- **`xmemory-admin`** — the **instance-management / control plane** (`/admin`): create, list, and
  manage instances and their schemas. Admin is global-only and cannot read or write the data inside
  instances; it includes destructive operations (e.g. deleting an instance), so it is a deliberate,
  separate connection.

Each connection authorizes via **OAuth 2.1 + PKCE** with dynamic client registration — a browser
opens on first use; **no static tokens are embedded in the shared listing**. A single server entry
holds one connection bound to **one** instance at a time (picked on the OAuth connect screen);
re-authorize to switch. For several instances at once, or for headless use, register one entry per
instance using the deep-link path and an API key from [console.xmemory.ai](https://console.xmemory.ai):
`https://mcp.xmemory.ai/instance/<instance_id>` with `Authorization: Bearer <xmem_... key>`
(the bare root is OAuth-only; the session type is determined by the URL path).

## The manifests

- [`xmemory.manifest.json`](./xmemory.manifest.json) — the data plane. Lists the 11 default
  instance tools (the opt-in schema-management group is granted only via the connect-page
  checkbox, so it is not advertised in the listing).
- [`xmemory-admin.manifest.json`](./xmemory-admin.manifest.json) — the control plane (25
  `admin_*` tools).

Both are modeled on the catalog's existing remote-OAuth entry (`linear__remote-mcp`): `server.type:
"remote"`, empty `client_id` (dynamic client registration), `supports_resource_metadata: true`
(Archestra walks `https://mcp.xmemory.ai/.well-known/oauth-protected-resource` →
`https://oauth2.xmemory.ai`). `scopes` / `default_scopes` are pinned to `["read", "write"]` — the
scopes our authorization server advertises in `scopes_supported` (verified live 2026-07-16; the AS
also advertises `openid`, which the listing does not request).

Both manifests also set `oauth_config.resource` (the registry form's **Protected Resource**) to
their server URL. Archestra does not derive it from `server_url`, and without it the xmemory
sign-in page loses the path hint: an admin connection shows the instance/admin chooser instead of
the admin confirmation, and an `/instance/<id>` connection loses its instance. The public catalog
API drops `oauth_config` fields its schema does not define, `resource` among them, so check
Protected Resource on any entry added from the catalog before authorizing it.

The manifests carry only fields the live schema defines. `github_info`, `programming_language` and
`readme` are `null`: the schema requires them, and none applies to a remote server. The fields the
catalog's retired evaluation pipeline used to fill (`quality_score`, `last_scraped_at`,
`evaluation_model`, `framework`, `raw_dependencies`, `score_breakdown`) are left out. The `icon` is
ours — see **Logo** below. `category: "Knowledge"` from their 38-value enum.

## Tools

### `xmemory` (memory)

The OAuth connect screen lets you choose exactly which tools to authorize; the schema-management
group starts unchecked. API-key connections get the default set. Instance tools return flat JSON
with a top-level `status` (`ok`/`error`) plus a `console_url` linking the operation in the console.
The synchronous `write` tool has a third value: `status: "still_processing"` means the wait ran out
while the write kept running. It is not a failure and must never be retried — a retry costs a second
extraction that then collides with the first. That object carries `write_id`, `trace_id` and
`message` in place of `console_url`; poll `write_status` once with the `write_id` for the outcome.

**Core memory** (granted by default)

| Tool | What it does |
|---|---|
| `write_async` | Preferred write path — save create/update/delete intent in natural language; returns immediately with a `write_id`. |
| `write` | Synchronous write; blocks until committed, so use it only when you must read the same data back in the same turn. |
| `read` | Query the instance in natural language (lookups, aggregations, listings, traversals). Not a free-text similarity search. |
| `write_status` | Diagnostic only — check once whether a specific async write landed, and how long it took. `queued`, `processing`, `extracting`, `extracted` and `applying` all mean it is still in flight. |
| `get_instance_id` | Return the instance ID for the current session. |
| `get_instance_schema` | Return the instance's object/field/relation schema. |
| `get_context_pack` | Return the bound instance's context pack with current owner instructions and optional live state. Needs `get_instance_schema` granted too. Live state is off by default; turning it on runs a billed read and needs the `read` grant. |
| `get_setup_instructions` | How to connect this instance on another surface; never returns a credential. |

There is no separate update or delete tool — writes express create, update, delete, and merge
intent in natural language ("her email changed to x@y", "delete the meeting with Bob on Friday"),
and the response's `changes` block reports exactly what was created, updated, and deleted.

**Schema evolution from real traffic** (granted by default)

| Tool | What it does |
|---|---|
| `review_suggestions` | See schema improvements proposed from your read/write traffic. |
| `decide_suggestions` | Accept / reject / defer those proposals (bulk). |
| `apply_pending_decisions` | Commit accepted proposals as a migration. |

**Schema management** (opt-in — unchecked by default, not part of this listing's advertised tools)

| Tool | What it does |
|---|---|
| `update_instance_schema` | Replace the schema (applied as a migration). |
| `dry_run_schema_migration` | Preview what `update_instance_schema` would do. |
| `list_schema_migrations` | Migration history, newest first. |
| `get_schema_migration` | One migration's detail. |
| `enhance_schema` | LLM improves a YAML schema from a description (returns YAML, does not apply). |

> The review / preview tools (`review_suggestions`, `dry_run_schema_migration`) are **read-only**;
> `decide_suggestions` → `apply_pending_decisions` and `update_instance_schema` commit a migration —
> an agent should confirm with you before applying.

### `xmemory-admin` (instance and key management)

Global account/fleet surface — no instance binding. Most admin tools return a JSON envelope whose
meaningful parts are `items` (the result) and `errors`; the schema and create tools, and every
tool's early-out error path, return a flat `{"status": ...}` shape instead. `admin_get_api_key` and
`admin_create_api_key` also return `{"status": "ok", "api_key": …}` flat, and `admin_list_api_keys`
returns the envelope. `admin_get_setup_instructions` returns its fields plus `status: "ok"` rather
than the envelope.

A connection lists only the admin tools its key's role permits. `admin_create_api_key` is offered
only on a connection that sends an account API key directly (`Authorization: Bearer xmem_...` on
`https://mcp.xmemory.ai/admin`), never on an OAuth install.

| Tool | What it does |
|---|---|
| `admin_create_instance` | Create a new instance. |
| `admin_list_instances`, `admin_list_own_instances` | List instances. |
| `admin_get_instance`, `admin_get_instance_by_id` | Inspect an instance. |
| `admin_get_instance_schema_by_id` | Read an instance's schema (observability). |
| `admin_get_setup_instructions` | How to connect a given instance on another surface; never returns a credential. |
| `admin_update_instance_metadata(_by_id)`, `admin_patch_instance_metadata(_by_id)` | Update name/description. |
| `admin_delete_instance`, `admin_delete_instance_by_id` | **Destructive** — permanently delete an instance. |
| `admin_list_instance_memberships` | List the cluster memberships of the instances you can see, with the revision an edit needs. |
| `admin_edit_instance_memberships` | Add or remove up to 100 instance–cluster memberships in one atomic change against that revision. Needs `instance.manage_clusters`; billing memberships cannot be removed. On a revision conflict, list again and review before retrying. |
| `admin_list_clusters`, `admin_get_cluster` | Cluster observability. |
| `admin_list_api_keys`, `admin_get_api_key`, `admin_create_api_key` | List and show the calling key's user's API keys (role, permissions, clusters, `is_super_admin`); create a limited key for one cluster (its secret is returned once). |
| `admin_list_mintable_roles` | The API roles a key minted by this key may have (`xmemcli org create key --role`). |
| `admin_generate_schema` | LLM: generate a fresh schema from a description. |
| `admin_enhance_schema` | LLM: improve an existing schema. |
| `admin_validate_yaml_schema` | Validate and repair schema YAML you already have (no LLM); returns `data_schema` and `schema_yaml`. |
| `admin_convert_json_schema` | Convert a JSON Schema object to XMD (no LLM); returns `data_schema` and `schema_yaml`. |

## Logo

[`logo.svg`](./logo.svg) is the xmemory mark. Archestra renders an entry's icon **from the manifest
itself** — catalog entries carry a `data:` URI rather than a URL — so the logo is inlined into each
manifest's `icon` field. SVG keeps that inline copy small (~1.8 KB as a data URI).

Because the bytes are duplicated into the JSON, `validate.py` checks that each manifest's `icon`
still matches `logo.svg`. After changing the logo, re-inline it:

```bash
python3 -c 'import base64,pathlib; p=pathlib.Path("logo.svg"); \
print("data:image/svg+xml;base64,"+base64.b64encode(p.read_bytes()).decode())'
```

## Testing the manifests

```
uv run --no-project --with jsonschema python validate.py
```

[`validate.py`](./validate.py) runs four checks (network required): JSON Schema validation against
the **live** catalog API's OpenAPI contract (`archestra.ai/mcp-catalog/api/docs` — the same spec
Archestra's codegen consumes, so it cannot drift), tool-list consistency against the in-repo sources
of truth (`api/instance_tool_catalog.py` default-on set, `ADMIN_ONLY_TOOLS` in `api/xmcp/server.py`),
description consistency against `api/describe.py` (first-party positioning verbatim in the main
manifest, admin management-only scope stated, and each tool one-liner sharing distinctive vocabulary
with its canonical `*_DESCRIPTION` headline), and liveness of every URL the manifests reference.
Re-run it whenever the MCP tool surface or descriptions change. The tool-list and description
checks need the xmemory monorepo sources; in this standalone mirror they are skipped with a notice
and the schema and URL checks still run.

For behavioral validation — that an Archestra deployment can actually install and use what the
manifests describe — run the private-registry recipe below against a local platform
(`docker run archestra/platform:latest`), which exercises OAuth discovery/DCR, tool discovery,
and a write→read round-trip.

## Using xmemory in an Archestra platform (private registry)

Org admins (permission `mcpRegistry:create`) can register the server directly, either flavor:

**OAuth (interactive users):** `/mcp/registry` → Add MCP Server → Start from scratch → type
**Remote**, server URL `https://mcp.xmemory.ai`, auth **OAuth**, Client ID empty (empty client id +
our discovered registration endpoint ⇒ dynamic client registration; redirect URI defaults to
`<platform-origin>/oauth-callback`). Equivalent API payload:

```json
{
  "name": "xmemory",
  "serverType": "remote",
  "serverUrl": "https://mcp.xmemory.ai",
  "oauthConfig": {
    "name": "xmemory",
    "server_url": "https://mcp.xmemory.ai",
    "resource": "https://mcp.xmemory.ai",
    "client_id": "",
    "redirect_uris": ["https://<your-archestra-host>/oauth-callback"],
    "scopes": ["read", "write"],
    "default_scopes": ["read", "write"],
    "supports_resource_metadata": true
  }
}
```

**Static API key (headless / instance-pinned):** bind the entry to one instance via the deep-link
URL and a bearer key — no browser flow. The `access_token` field below declares `headerName` /
`valuePrefix` explicitly. Archestra would fall back to `Authorization: Bearer <access_token>` for
this field name anyway, but being explicit documents the contract and keeps working if the field is
ever renamed:

```json
{
  "name": "xmemory",
  "serverType": "remote",
  "serverUrl": "https://mcp.xmemory.ai/instance/<instance-id>",
  "userConfig": {
    "access_token": {
      "type": "string",
      "title": "xmemory API key",
      "description": "Account API key (xmem_...) from console.xmemory.ai",
      "required": true,
      "sensitive": true,
      "headerName": "Authorization",
      "valuePrefix": "Bearer "
    }
  }
}
```

Never embed a real key in a shared listing; the key is prompted for at install time. Note that each
Archestra OAuth install re-runs dynamic client registration (one registered client per install).

## Support & legal

- Docs: https://xmemory.ai/mcp
- Privacy: https://xmemory.ai/privacy-policy.html
- Terms: https://xmemory.ai/terms-and-conditions.html

© xmemory Inc. This listing — the manifests, the validation tooling, and the documentation — is
released under the [MIT License](./LICENSE). The xmemory service it connects to, and the technology
behind it, remain proprietary; see [`NOTICE`](./NOTICE) for the scope of the license and the
trademark terms. Use of xmemory is governed by the
[Terms & Conditions](https://xmemory.ai/terms-and-conditions.html).
