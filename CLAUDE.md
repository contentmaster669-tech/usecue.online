# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Built and passing: 49 tests, `ruff` clean. Migrations 001–003 have been run against the live Supabase project and `verify.sql` passed all 21 checks.

**Verified against live services**, not just mocks:

- Key issuance → Supabase write works (`scripts/issue_key.py`).
- `GET /mcp` returns **405** — the FastMCP SSE-hang bug is genuinely blocked.
- `initialize`, `tools/list`, and `cue_status` all work over real HTTP.
- `check_usage` returns `Cue — Free — 5/5 checks and 3/3 rewrites left today.` — this exercised the whole chain (key → sha256 → Supabase → `get_quota` RPC → column unpacking), so the RPC return shapes match what Python expects.

**Still unproven: live detection.** The OpenAI key authenticates but has **no credits** (`429 insufficient_quota`), so `analyze_message` has never completed a real call. `responses.parse()` against the master prompt is untested. See "Timeout is unmeasured" below.

Remaining: Phase 5 (quota race fix), Phase 7 (model benchmark), Phase 8 (cross-client validation). Phase 6's throttle is now done; `detection_events` logging is not. The approved plan at `C:\Users\User\.claude\plans\plan-an-mcp-model-dazzling-valiant.md` holds the full build order.

## Naming: "Cue" is the product, `callyr` is the package

The product was renamed from CALLYR to **Cue** (domain: `usecue.online`). Every user-facing string says Cue. Internal identifiers deliberately still say `callyr`:

- The `callyr/` Python package, its imports, and `[tool.vercel] entrypoint` — renaming means a reinstall and redeploy for no functional gain.
- The `callyr.*` logger names and the `callyr_api_key` ContextVar.

All three **MCP tool names are user-visible** and say Cue: `cue_status`, `analyze_message`, `check_usage`. Tool names are wire-protocol identifiers — renaming one breaks every already-connected client, so treat further changes as a migration, not a refactor.

Do not "finish" this rename without a deliberate migration. When adding user-facing text, write Cue.

## What Cue is

A hosted MCP server that detects sycophancy (an AI agreeing to please) and hallucination (confident falsehoods) in AI responses. Users connect it once via their AI app's connector settings. The host model calls `analyze_message` with its own draft answer; Cue runs a master detection prompt through `gpt-4o-mini` and returns either a two-line alert + rewritten prompt, or **nothing at all**.

## Non-obvious constraints — read before designing anything

Each was verified against current docs and contradicts an intuitive assumption:

1. **MCP cannot silently intercept AI responses.** It is a pull protocol; the client decides when to call. There is no per-message hook. Near-passive operation comes only from `analyze_message`'s tool *description* persuading the host model to self-audit (`TOOL_DESCRIPTION` in `callyr/tools/analyze.py`). Do not design anything that assumes interception.

2. **`serverInfo` is not rendered by Claude's connector UI.** The connector name shown in Settings is whatever the user typed when adding the URL. The Active Indicator is therefore the **`cue_status` tool** — its presence in the tools panel *is* the signal. `serverInfo` is populated anyway as a no-cost fallback, but nothing may depend on it.

3. **Silence is the product.** When nothing is detected the tool returns `""` — empty string, not a "looks good" message. Tests assert `== ""` explicitly, not falsiness. A chatty Cue is a failed Cue.

4. **Fail-silent, always.** OpenAI timeout (8s hard cap), API error, malformed output, unknown API key, database unreachable, or any unhandled exception → return `""`, indistinguishable from "nothing detected." Errors are logged server-side and never surface into the user's conversation. This makes misconfiguration genuinely hard to diagnose — check server logs, not tool output.

5. **Stateless HTTP is mandatory, not a preference.** Serverless has no session affinity, so MCP sessions cannot survive across invocations. Hence `mcp.http_app(stateless_http=True, path="/mcp")` and the ContextVar in `callyr/auth/context.py` rather than session state.

## API and library gotchas

Current correct forms — each has a plausible-looking stale alternative in older examples:

| Use | Not |
|---|---|
| `mcp.http_app()` | `mcp.streamable_http_app()` (deprecated) |
| standalone `fastmcp` package | `mcp[cli]` |
| `supabase` + `acreate_client` | `supabase-py-async` (obsolete) |
| `client.responses.parse()` | `client.beta.chat.completions.parse()` |

**FastMCP stateless bug:** stateless mode still accepts GET on `/mcp` and opens a long-lived SSE stream instead of returning 405 ([fastmcp#3179](https://github.com/PrefectHQ/fastmcp/issues/3179)). On serverless that is a function hanging on the billing clock. `AuthMiddleware` rejects GET on the MCP path explicitly — do not remove that check.

## Architecture

ASGI app exported as `callyr.server:app` (declared in `pyproject.toml` under `[tool.vercel]`). Request path:

```
Vercel → AuthMiddleware (GET-block, key extraction from /mcp/<key>)
       → FastMCP stateless HTTP
       → tool (cue_status | analyze_message | check_usage)
       → db (identity → quota gate) → OpenAI Responses API
       → detection/engine (format, or "")
```

Layer responsibilities:

- `callyr/config.py` — **every** tunable: model string, timeouts, quota limits, price, server identity. `MODEL` lives here alone so Phase 7's benchmark swaps models in one line. Never hardcode `"gpt-4o-mini"` anywhere else.
- `callyr/tools/` — thin MCP surface. Each module defines its logic at **module level** and `register(mcp)` only wraps it, so tools stay directly callable and testable. Do not nest tool bodies inside `register()`.
- `callyr/detection/` — prompt → OpenAI → Pydantic parse → format.
- `callyr/auth/` — path-based API keys, sha256-hashed, `hmac.compare_digest`.
- `callyr/db/` — Supabase via the secret key; all quota and throttle math in Postgres.
- `callyr/utils/validation.py` — type checks and length caps, applied before any API call or DB write.

## The prompt/schema contract (looks contradictory on purpose)

`prompts/master_detection_prompt.py` holds the master prompt **verbatim** and must not be edited, reworded, or reformatted.

Its PART 4 tells the model to emit a formatted text block, but the engine does **not** parse that. Detection uses `responses.parse()` with the `Detection` schema (`detected`, `problem_type`, `alert_line`, `better_prompt`). PART 4 is the *semantic* contract (what to say); the schema is the *delivery* mechanism.

Never "fix" this in either direction. Structured fields are what make the alert-without-rewrite quota state expressible, and what make silence a reliable `detected: false` rather than depending on the model returning a literally empty string.

## Data model decisions

- **Daily quota reset needs no cron.** `daily_usage` is keyed `(user_id, usage_date)`, so a new day is simply a new row; yesterday's goes inert. No scheduled job to fail.
- **Quota math happens in Postgres** — `consume_quota` upserts and increments under one row lock. In application code this creates a race where concurrent calls both read "1 left" and both proceed.
- **`detection_events` stores no conversation content** — metadata only. Cue sees users' private chats (including doctors'); a deliberate privacy boundary, not an oversight. Do not add message columns.
- **RLS is deny-by-default**: enabled *and* forced on all tables, with zero policies and grants revoked from `anon`/`authenticated`. The service role is the only path in.
- **Free-tier limits are duplicated** — `config.py` and the `_free_daily_checks()`/`_free_daily_rewrites()` SQL functions. The database is authoritative; Python only displays. Change both together.

## Quota behavior

Checks (5/day) and rewrites (3/day) are tracked **separately**, producing four states:

| Checks | Rewrites | Output |
|---|---|---|
| left | left | alert + rewritten prompt |
| left | **exhausted** | alert + `Upgrade to Pro for the rewritten prompt.` |
| **exhausted** | — | `Cue daily limit reached — upgrade for unlimited.` once/day, then silent |
| pro | pro | always full output |

`-1` is the unlimited sentinel for pro — `QuotaState.has_check` tests `!= 0`, so never treat these counters as booleans. The limit notice fires once per day per user (`limit_notice_shown_on`) so it never becomes a nag.

**Order matters for cost:** identity → quota → OpenAI. An out-of-quota user must never reach the API. `tests/test_quota.py::test_exhausted_never_calls_openai` guards this.

## Abuse throttle

30 requests/minute, counted in Postgres by `record_request()` (`004_throttle.sql`), which `get_quota` calls on every read. Applies to **pro accounts too** — it is abuse prevention, not a billing limit.

Enforced in every tool that touches the database: `analyze_message` and `check_usage`. `cue_status` needs none because it touches nothing — static string, no DB, no API.

`request_log` self-cleans opportunistically (~2% of calls delete rows older than an hour) so it never grows without bound.

## Input validation

`ai_response` and `user_message` have **separate** caps — 10,000 and 5,000 chars (`config.MAX_AI_RESPONSE_CHARS` / `MAX_USER_QUERY_CHARS`). An answer is typically far longer than the question, so one shared limit would either truncate answers or over-admit queries.

MCP arguments arrive as JSON, so a client can send **any type** where a string is declared. `clamp()` rejects non-strings with `isinstance` rather than coercing — coercion would send `str(dict)` to the model and bill the user for nonsense. Oversized input is truncated, never rejected: a rejection would surface an error, and Cue never shows errors.

## Known gaps (deliberate, scheduled)

- **Quota is consumed after the API call**, so a failed call costs the user nothing — but concurrent requests can exceed the daily cap, since the gate reads before any increment. The throttle bounds how badly, but does not fix it. Phase 5: reserve-then-refund.
- **The 8s OpenAI timeout is unmeasured.** No real detection call has ever completed, so nothing confirms 8s is enough for a ~10KB prompt plus schema-constrained generation. A timeout returns `""` — **indistinguishable from "clean"** — so if it is too tight, production fails invisibly. `scratchpad/timeout_probe.py` measures real latency across three runs and prints a verdict; run it once credits are loaded, then set the cap from measured p95. Note a *quota rejection* took 9.66s to come back, which is already past the cap.
- **`detection_events` is never written to.** No event logging yet.

## Prompt injection

`ai_response` is untrusted user-adjacent content. It is passed as a separate structured input field wrapped in `<ai_response>` tags — never concatenated into the system prompt. Keep it that way.

## Commands

```bash
pip install -e ".[dev]"          # install with dev deps
pytest                           # all tests
pytest tests/test_quota.py       # one file
pytest -k silence                # the tests that matter most
ruff check . && ruff format .    # lint + format
python scripts/issue_key.py you@example.com   # mint an API key (no signup page yet)
vercel dev                       # local serverless emulation
vercel --prod                    # deploy
```

```bash
python -m uvicorn callyr.server:app --port 8899   # run locally over real HTTP
curl -i http://127.0.0.1:8899/mcp                 # must be 405, not a hanging SSE stream
```

Database setup: run `supabase/migrations/` 001 → 004 in order, then `supabase/verify.sql` to confirm. **004 is the throttle** — until it runs, `get_quota` returns `throttled => false` and the limit is unenforced even though the Python side checks it.

Environment (`.env.example` → `.env`): `OPENAI_API_KEY`, `SUPABASE_URL`, and the Supabase **secret** key. Supabase renamed these in 2026 — `sb_secret_…` replaces the legacy `service_role` JWT and is a drop-in substitute needing no code change. `config.py` accepts four spellings in order: `SUPABASE_SECRET_KEY`, `SUPABASE_SERVICE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_KEY`.

It must be the secret key, never the publishable one — RLS is deny-by-default, so the publishable key reads zero rows and every lookup fails silently.

## Repo layout note

`site/` is a standalone static landing page — strictly monochrome, JetBrains Mono only, no build step. It is unrelated to the MCP server and excluded from the Vercel function bundle. Its palette is verifiably achromatic (R=G=B on every hex); keep it that way.
