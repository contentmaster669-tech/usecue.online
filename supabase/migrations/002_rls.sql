-- Row-level security: deny by default.
--
-- RLS is enabled on every table and NO permissive policies are created. With
-- RLS on and zero policies, every row is invisible to anon and authenticated.
-- The service role bypasses RLS entirely, so the MCP server is the only path
-- in. If the anon key leaks, it reads nothing.
--
-- Do not add a permissive policy here without a specific reason. "It didn't
-- work in the dashboard" is not one -- the dashboard uses anon by design.

alter table public.users            enable row level security;
alter table public.daily_usage      enable row level security;
alter table public.request_log      enable row level security;
alter table public.detection_events enable row level security;

-- Force RLS for the table owner too, so a misconfigured connection cannot
-- quietly bypass it. (Service role still bypasses, as intended.)
alter table public.users            force row level security;
alter table public.daily_usage      force row level security;
alter table public.request_log      force row level security;
alter table public.detection_events force row level security;

-- Belt and braces: revoke the default grants Supabase hands to anon and
-- authenticated on new tables in the public schema.
revoke all on public.users            from anon, authenticated;
revoke all on public.daily_usage      from anon, authenticated;
revoke all on public.request_log      from anon, authenticated;
revoke all on public.detection_events from anon, authenticated;
