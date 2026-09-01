-- Per-minute abuse throttle, actually enforced.
--
-- Before this migration, get_quota/consume_quota returned `throttled => false`
-- unconditionally and request_log was never written. The Python check existed
-- but could never fire. This makes it real.
--
-- Counting happens in Postgres for the same reason quota does: a read-then-write
-- in application code lets concurrent requests each see "under the limit" and
-- all proceed.

create or replace function public._throttle_per_minute() returns int
language sql immutable as $$ select 30; $$;


-- Record one request and report whether the caller is now over the limit.
-- Returns true when the request should be REFUSED.
create or replace function public.record_request(p_user_id uuid)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_recent int;
begin
  insert into public.request_log (user_id) values (p_user_id);

  select count(*) into v_recent
  from public.request_log
  where user_id = p_user_id
    and created_at > now() - interval '1 minute';

  -- Opportunistic cleanup: keep the table from growing without bound. Runs
  -- rarely (roughly 1 in 50 calls) so it never dominates a request.
  if random() < 0.02 then
    delete from public.request_log
    where created_at < now() - interval '1 hour';
  end if;

  return v_recent > public._throttle_per_minute();
end;
$$;


-- get_quota now reports a real throttle state instead of a literal false.
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
  v_plan      text;
  v_throttled boolean;
begin
  select case
           when u.plan = 'pro' and u.plan_expires_at is not null
                and u.plan_expires_at < now()
           then 'free' else u.plan
         end
  into v_plan
  from public.users u
  where u.id = p_user_id and not u.revoked;

  if v_plan is null then
    return;  -- unknown or revoked user: no rows, caller treats as not-ok
  end if;

  -- Every quota read is a request, so this is the natural place to count.
  -- Applies to pro as well -- it is abuse prevention, not a billing limit.
  select public.record_request(p_user_id) into v_throttled;

  return query
  select
    v_plan,
    public._quota_left(v_plan, coalesce(d.checks_used, 0), public._free_daily_checks()),
    public._quota_left(v_plan, coalesce(d.rewrites_used, 0), public._free_daily_rewrites()),
    v_throttled
  from (select 1) _
  left join public.daily_usage d
    on d.user_id = p_user_id and d.usage_date = current_date;
end;
$$;


revoke all on function public.record_request(uuid) from public, anon, authenticated;
grant execute on function public.record_request(uuid) to service_role;
