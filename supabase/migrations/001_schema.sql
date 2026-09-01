-- Cue core schema.
--
-- Privacy boundary: no table here stores conversation content. Cue sees
-- users' private chats (including doctors'); metadata only is deliberate.
-- Do not add message columns.

create extension if not exists pgcrypto;

-- Accounts. The raw API key is never stored, only its sha256 hash.
create table if not exists public.users (
  id              uuid primary key default gen_random_uuid(),
  email           text unique not null,
  api_key_hash    text unique not null,
  key_prefix      text not null,                    -- first 8 chars, for support lookups
  plan            text not null default 'free'
                    check (plan in ('free', 'pro')),
  plan_expires_at timestamptz,                      -- null for free; set by billing later
  created_at      timestamptz not null default now(),
  revoked         boolean not null default false
);

-- Hot path: every request resolves a key to a user id.
create index if not exists users_api_key_hash_active_idx
  on public.users (api_key_hash)
  where not revoked;

-- Daily quota. Keyed (user_id, usage_date) so a new day is simply a new row
-- and yesterday's goes inert -- no cron job to reset, none to fail.
create table if not exists public.daily_usage (
  user_id               uuid not null references public.users(id) on delete cascade,
  usage_date            date not null default current_date,
  checks_used           int  not null default 0,
  rewrites_used         int  not null default 0,
  limit_notice_shown_on date,                       -- once-per-day upgrade notice
  primary key (user_id, usage_date)
);

-- Per-minute abuse throttle. One row per request; Phase 6 enforces against it.
create table if not exists public.request_log (
  id         bigserial primary key,
  user_id    uuid not null references public.users(id) on delete cascade,
  created_at timestamptz not null default now()
);

create index if not exists request_log_user_recent_idx
  on public.request_log (user_id, created_at desc);

-- Analytics. Metadata only -- deliberately no message content.
create table if not exists public.detection_events (
  id            bigserial primary key,
  user_id       uuid not null references public.users(id) on delete cascade,
  occurred_at   timestamptz not null default now(),
  problem_type  text,                               -- sycophancy|hallucination|both|none
  detected      boolean not null,
  client_hint   text,                               -- claude|chatgpt|perplexity|grok
  latency_ms    int,
  input_tokens  int,
  output_tokens int
);

create index if not exists detection_events_user_time_idx
  on public.detection_events (user_id, occurred_at desc);
