-- Quota RPCs.
--
-- Increments happen HERE, not in application code. Doing the read-then-write
-- in Python creates a race where two concurrent MCP calls both read "1 left"
-- and both proceed. The upsert below increments under a single row lock.
--
-- All three functions are SECURITY DEFINER so they run as owner and bypass
-- RLS, with an empty search_path to prevent search-path hijacking.

-- Free-tier limits live in one place per side: config.py in Python, here in
-- SQL. Keep these two in sync -- if they drift, Python's display will disagree
-- with what the database actually enforces (the database wins).
create or replace function public._free_daily_checks() returns int
language sql immutable as $$ select 5; $$;

create or replace function public._free_daily_rewrites() returns int
language sql immutable as $$ select 3; $$;


-- Remaining quota for a plan, given today's usage.
-- Returns -1 for unlimited (pro).
create or replace function public._quota_left(
  p_plan text,
  p_used int,
  p_limit int
) returns int
language sql
immutable
as $$
  select case when p_plan = 'pro' then -1 else greatest(p_limit - p_used, 0) end;
$$;


-- Read plan and remaining quota WITHOUT consuming any.
create or replace function public.get_quota(p_user_id uuid)
returns table (
  plan          text,
  checks_left   int,
  rewrites_left int,
  throttled     boolean
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_plan text;
begin
  select u.plan into v_plan
  from public.users u
  where u.id = p_user_id and not u.revoked;

  if v_plan is null then
    return;  -- unknown or revoked user: no rows, caller treats as not-ok
  end if;

  -- Pro plans that have lapsed fall back to free.
  select case
           when v_plan = 'pro' and u.plan_expires_at is not null
                and u.plan_expires_at < now()
           then 'free' else v_plan
         end
  into v_plan
  from public.users u
  where u.id = p_user_id;

  return query
  select
    v_plan,
    public._quota_left(v_plan, coalesce(d.checks_used, 0), public._free_daily_checks()),
    public._quota_left(v_plan, coalesce(d.rewrites_used, 0), public._free_daily_rewrites()),
    false  -- throttle computed in Phase 6; always false for now
  from (select 1) _
  left join public.daily_usage d
    on d.user_id = p_user_id and d.usage_date = current_date;
end;
$$;


-- Consume one unit of quota atomically and return the resulting state.
-- p_kind is 'check' or 'rewrite'.
create or replace function public.consume_quota(
  p_user_id uuid,
  p_kind    text
)
returns table (
  plan          text,
  checks_left   int,
  rewrites_left int,
  throttled     boolean
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_plan     text;
  v_checks   int;
  v_rewrites int;
begin
  if p_kind not in ('check', 'rewrite') then
    raise exception 'consume_quota: p_kind must be check or rewrite, got %', p_kind;
  end if;

  select case
           when u.plan = 'pro' and u.plan_expires_at is not null
                and u.plan_expires_at < now()
           then 'free' else u.plan
         end
  into v_plan
  from public.users u
  where u.id = p_user_id and not u.revoked;

  if v_plan is null then
    return;
  end if;

  -- Upsert today's row and increment under one lock. Concurrent callers
  -- serialize on the primary key, so the last unit cannot be spent twice.
  insert into public.daily_usage (user_id, usage_date, checks_used, rewrites_used)
  values (
    p_user_id,
    current_date,
    case when p_kind = 'check'   then 1 else 0 end,
    case when p_kind = 'rewrite' then 1 else 0 end
  )
  on conflict (user_id, usage_date) do update
    set checks_used = public.daily_usage.checks_used
                      + case when p_kind = 'check'   then 1 else 0 end,
        rewrites_used = public.daily_usage.rewrites_used
                      + case when p_kind = 'rewrite' then 1 else 0 end
  returning daily_usage.checks_used, daily_usage.rewrites_used
  into v_checks, v_rewrites;

  return query select
    v_plan,
    public._quota_left(v_plan, v_checks, public._free_daily_checks()),
    public._quota_left(v_plan, v_rewrites, public._free_daily_rewrites()),
    false;
end;
$$;


-- Claim the once-per-day limit notice. Returns true at most once per user per
-- day, so the upgrade line never becomes a nag.
create or replace function public.claim_limit_notice(p_user_id uuid)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_claimed boolean := false;
begin
  insert into public.daily_usage (user_id, usage_date, limit_notice_shown_on)
  values (p_user_id, current_date, current_date)
  on conflict (user_id, usage_date) do update
    set limit_notice_shown_on = current_date
    where public.daily_usage.limit_notice_shown_on is distinct from current_date
  returning true into v_claimed;

  return coalesce(v_claimed, false);
end;
$$;


-- Only the service role may execute these.
revoke all on function public.get_quota(uuid)                 from public, anon, authenticated;
revoke all on function public.consume_quota(uuid, text)       from public, anon, authenticated;
revoke all on function public.claim_limit_notice(uuid)        from public, anon, authenticated;
grant execute on function public.get_quota(uuid)              to service_role;
grant execute on function public.consume_quota(uuid, text)    to service_role;
grant execute on function public.claim_limit_notice(uuid)     to service_role;
