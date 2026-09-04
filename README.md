# Cue — AI Honesty Guardian

An MCP server that detects sycophancy (an AI agreeing to please) and
hallucination (confident falsehoods) in AI responses. When a problem is found
it returns a short alert plus one rewritten prompt, in the user's own language.
When nothing is wrong it returns nothing at all.

Silence is the product.

## Tools

| Tool | Cost | Purpose |
|---|---|---|
| `cue_status` | free | Active Indicator. Static string, no API or DB call. |
| `analyze_message` | 1 check | Audits a draft response. Returns `""` unless a problem is found. |
| `check_usage` | free | Remaining daily quota and plan. |

## Setup

```bash
pip install -e ".[dev]"
cp .env.example .env        # then fill in the three values
```

Run the migrations in `supabase/migrations/` against your Supabase project,
in order (001, 002, 003) — the SQL editor works fine.

Issue yourself a key:

```bash
python scripts/issue_key.py you@example.com
```

The raw key prints once and is not recoverable. Your connector URL is
`https://usecue.online/mcp`, which is what users paste into their AI
header. Both go into your AI app's connector settings.

## Development

```bash
pytest                       # all tests
pytest tests/test_quota.py   # one file
pytest -k silence            # the tests that matter most
ruff check . && ruff format .
vercel dev                   # local serverless emulation
vercel --prod                # deploy
```

## Environment

| Variable | Notes |
|---|---|
| `OPENAI_API_KEY` | Detection calls. |
| `SUPABASE_URL` | Project URL. |
| `SUPABASE_SERVICE_KEY` | Must be the **service role** key — RLS is deny-by-default, so the anon key reads zero rows. `SUPABASE_KEY` is accepted as an alias. |

## Design notes

Two constraints shape everything, and both contradict the obvious assumption:

**MCP cannot intercept AI responses.** It is a pull protocol — the client
decides when to call, and there is no per-message hook. Near-passive operation
comes only from `analyze_message`'s tool *description* persuading the host
model to self-audit. Claude complies reliably; other clients less so.

**`serverInfo` is not rendered by Claude's connector UI.** The name shown in
Settings is whatever the user typed when adding the URL. That is why the
Active Indicator is a *tool* — its presence in the tools panel is the signal.

See `CLAUDE.md` for the full set of non-obvious constraints.
