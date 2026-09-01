-- Cue migration verification.
--
-- Run AFTER 001, 002, 003. Paste the whole file into the Supabase SQL editor.
-- Every check prints PASS or FAIL. Read the last result set: zero FAIL rows
-- means the schema, RLS, and quota logic are all behaving.
--
-- Safe to re-run. It creates a temporary test user, exercises the quota
-- functions against it, and deletes it at the end.
--
-- IMPORTANT: the SQL editor runs as a privileged role that BYPASSES RLS.
-- A plain "select * from users" here returns rows even when RLS is correct.
-- The RLS section below switches to the anon role explicitly -- that is the
-- only way to test deny-by-default without a false pass.

do $$
declare
  v_user   uuid;
  v_plan   text;
  v_checks int;
  v_rw     int;
  v_bool   boolean;
  v_count  int;
  v_fails  int := 0;
  v_tbl    text;
begin
  create temp table if not exists _verify (
    section text,
    check_name text,
    result text,
    detail text
  ) on commit preserve rows;
  delete from _verify;

  ---------------------------------------------------------------- schema ----
  foreach v_tbl in array array['users','daily_usage','request_log','detection_events']
  loop
    select count(*) into v_count
    from information_schema.tables
    where table_schema = 'public' and table_name = v_tbl;

    insert into _verify values (
      '1. schema',
      'table ' || v_tbl || ' exists',
      case when v_count = 1 then 'PASS' else 'FAIL' end,
      null
    );
    if v_count <> 1 then v_fails := v_fails + 1; end if;
  end loop;

  -- The privacy boundary: detection_events must hold no message content.
  select count(*) into v_count
  from information_schema.columns
  where table_schema = 'public'
    and table_name = 'detection_events'
    and column_name in ('message','content','user_message','ai_response','text','prompt');

  insert into _verify values (
    '1. schema',
    'detection_events stores no conversation content',
    case when v_count = 0 then 'PASS' else 'FAIL' end,
    case when v_count = 0 then null else v_count || ' content column(s) found' end
  );
  if v_count <> 0 then v_fails := v_fails + 1; end if;

  -- Composite key is what makes daily reset cron-free.
  select count(*) into v_count
  from information_schema.key_column_usage k
  join information_schema.table_constraints t
    on t.constraint_name = k.constraint_name
  where t.table_schema = 'public'
    and t.table_name = 'daily_usage'
    and t.constraint_type = 'PRIMARY KEY';

  insert into _verify values (
    '1. schema',
    'daily_usage PK is (user_id, usage_date)',
    case when v_count = 2 then 'PASS' else 'FAIL' end,
    'columns in PK: ' || v_count
  );
  if v_count <> 2 then v_fails := v_fails + 1; end if;

  ------------------------------------------------------------------- rls ----
  select count(*) into v_count
  from pg_tables
  where schemaname = 'public'
    and tablename in ('users','daily_usage','request_log','detection_events')
    and rowsecurity;

  insert into _verify values (
    '2. rls',
    'RLS enabled on all 4 tables',
    case when v_count = 4 then 'PASS' else 'FAIL' end,
    v_count || '/4 enabled'
  );
  if v_count <> 4 then v_fails := v_fails + 1; end if;

  -- Deny-by-default means RLS on with ZERO permissive policies. Any policy
  -- here is a hole unless it was added deliberately.
  select count(*) into v_count
  from pg_policies
  where schemaname = 'public'
    and tablename in ('users','daily_usage','request_log','detection_events');

  insert into _verify values (
    '2. rls',
    'no permissive policies exist (deny-by-default)',
    case when v_count = 0 then 'PASS' else 'FAIL' end,
    v_count || ' policies found'
  );
  if v_count <> 0 then v_fails := v_fails + 1; end if;

  -- FORCE means even the table owner cannot bypass.
  select count(*) into v_count
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public'
    and c.relname in ('users','daily_usage','request_log','detection_events')
    and c.relforcerowsecurity;

  insert into _verify values (
    '2. rls',
    'FORCE row level security on all 4 tables',
    case when v_count = 4 then 'PASS' else 'FAIL' end,
    v_count || '/4 forced'
  );
  if v_count <> 4 then v_fails := v_fails + 1; end if;

  ------------------------------------------------------- quota functions ----
  insert into public.users (email, api_key_hash, key_prefix, plan)
  values ('_verify@callyr.test', 'verify-hash-' || gen_random_uuid(), 'verify00', 'free')
  returning id into v_user;

  -- Fresh user: full free quota, nothing consumed.
  select plan, checks_left, rewrites_left into v_plan, v_checks, v_rw
  from public.get_quota(v_user);

  insert into _verify values (
    '3. quota',
    'new free user starts at 5 checks / 3 rewrites',
    case when v_plan = 'free' and v_checks = 5 and v_rw = 3 then 'PASS' else 'FAIL' end,
    format('plan=%s checks=%s rewrites=%s', v_plan, v_checks, v_rw)
  );
  if not (v_plan = 'free' and v_checks = 5 and v_rw = 3) then v_fails := v_fails + 1; end if;

  -- get_quota must not consume.
  select checks_left into v_checks from public.get_quota(v_user);
  insert into _verify values (
    '3. quota',
    'get_quota consumes nothing when called twice',
    case when v_checks = 5 then 'PASS' else 'FAIL' end,
    'checks after 2 reads: ' || v_checks
  );
  if v_checks <> 5 then v_fails := v_fails + 1; end if;

  -- consume_quota decrements the right counter, and only that one.
  select checks_left, rewrites_left into v_checks, v_rw
  from public.consume_quota(v_user, 'check');

  insert into _verify values (
    '3. quota',
    'consume check: 5->4, rewrites untouched',
    case when v_checks = 4 and v_rw = 3 then 'PASS' else 'FAIL' end,
    format('checks=%s rewrites=%s', v_checks, v_rw)
  );
  if not (v_checks = 4 and v_rw = 3) then v_fails := v_fails + 1; end if;

  select checks_left, rewrites_left into v_checks, v_rw
  from public.consume_quota(v_user, 'rewrite');

  insert into _verify values (
    '3. quota',
    'consume rewrite: 3->2, checks untouched',
    case when v_checks = 4 and v_rw = 2 then 'PASS' else 'FAIL' end,
    format('checks=%s rewrites=%s', v_checks, v_rw)
  );
  if not (v_checks = 4 and v_rw = 2) then v_fails := v_fails + 1; end if;

  -- Floor at zero: exhausting must not go negative.
  perform public.consume_quota(v_user, 'check');
  perform public.consume_quota(v_user, 'check');
  perform public.consume_quota(v_user, 'check');
  perform public.consume_quota(v_user, 'check');
  perform public.consume_quota(v_user, 'check');
  select checks_left into v_checks from public.get_quota(v_user);

  insert into _verify values (
    '3. quota',
    'exhausted quota floors at 0, never negative',
    case when v_checks = 0 then 'PASS' else 'FAIL' end,
    'checks_left = ' || v_checks
  );
  if v_checks <> 0 then v_fails := v_fails + 1; end if;

  -- Bad kind must raise, not silently miscount.
  begin
    perform public.consume_quota(v_user, 'nonsense');
    insert into _verify values (
      '3. quota', 'consume_quota rejects an invalid kind', 'FAIL',
      'no exception raised'
    );
    v_fails := v_fails + 1;
  exception when others then
    insert into _verify values (
      '3. quota', 'consume_quota rejects an invalid kind', 'PASS', null
    );
  end;

  ----------------------------------------------------- once-per-day notice --
  select public.claim_limit_notice(v_user) into v_bool;
  insert into _verify values (
    '4. limit notice',
    'first claim returns true',
    case when v_bool then 'PASS' else 'FAIL' end,
    'returned ' || v_bool
  );
  if not v_bool then v_fails := v_fails + 1; end if;

  select public.claim_limit_notice(v_user) into v_bool;
  insert into _verify values (
    '4. limit notice',
    'second claim same day returns false (never a nag)',
    case when not v_bool then 'PASS' else 'FAIL' end,
    'returned ' || v_bool
  );
  if v_bool then v_fails := v_fails + 1; end if;

  ------------------------------------------------------------------- pro ----
  update public.users set plan = 'pro' where id = v_user;
  select plan, checks_left, rewrites_left into v_plan, v_checks, v_rw
  from public.get_quota(v_user);

  insert into _verify values (
    '5. pro plan',
    'pro reports unlimited (-1) despite exhausted free counters',
    case when v_plan = 'pro' and v_checks = -1 and v_rw = -1 then 'PASS' else 'FAIL' end,
    format('plan=%s checks=%s rewrites=%s', v_plan, v_checks, v_rw)
  );
  if not (v_plan = 'pro' and v_checks = -1 and v_rw = -1) then v_fails := v_fails + 1; end if;

  -- A lapsed pro must fall back to free, not stay unlimited.
  update public.users
  set plan = 'pro', plan_expires_at = now() - interval '1 day'
  where id = v_user;
  select plan into v_plan from public.get_quota(v_user);

  insert into _verify values (
    '5. pro plan',
    'expired pro falls back to free',
    case when v_plan = 'free' then 'PASS' else 'FAIL' end,
    'plan reported as ' || v_plan
  );
  if v_plan <> 'free' then v_fails := v_fails + 1; end if;

  ------------------------------------------------------------- revoked ------
  update public.users set revoked = true, plan = 'free', plan_expires_at = null
  where id = v_user;

  select count(*) into v_count from public.get_quota(v_user);
  insert into _verify values (
    '6. revoked',
    'revoked user gets no quota rows',
    case when v_count = 0 then 'PASS' else 'FAIL' end,
    v_count || ' rows returned'
  );
  if v_count <> 0 then v_fails := v_fails + 1; end if;

  ------------------------------------------------------------- cleanup ------
  delete from public.users where id = v_user;
end $$;


-- ---------------------------------------------------------------------------
-- RLS deny-by-default, tested as the anon role.
--
-- This runs OUTSIDE the block above because it switches role. The editor's
-- default role bypasses RLS, so this is the only section that proves anon
-- actually reads nothing.
-- ---------------------------------------------------------------------------
do $$
declare
  v_count int;
  v_denied boolean := false;
begin
  set local role anon;

  begin
    select count(*) into v_count from public.users;
    v_denied := (v_count = 0);
  exception when insufficient_privilege then
    v_denied := true;  -- permission denied is an even stronger pass
  end;

  reset role;

  insert into _verify values (
    '2. rls',
    'anon role reads ZERO rows from users',
    case when v_denied then 'PASS' else 'FAIL' end,
    case when v_denied then null else 'anon saw ' || v_count || ' row(s) -- RLS IS NOT WORKING' end
  );
end $$;


-- Summary, counted across every check including the anon RLS test above.
do $$
declare
  v_fails int;
begin
  select count(*) into v_fails from _verify where result = 'FAIL';
  insert into _verify values (
    'summary',
    case when v_fails = 0 then 'ALL CHECKS PASSED' else v_fails || ' CHECK(S) FAILED' end,
    case when v_fails = 0 then 'PASS' else 'FAIL' end,
    null
  );
end $$;


-- ---------------------------------------------------------------------------
-- Results. Read this table; FAIL rows name what broke.
-- ---------------------------------------------------------------------------
select section, check_name, result, coalesce(detail, '') as detail
from _verify
order by
  case when section = 'summary' then 2 else 1 end,
  section,
  check_name;
