-- Run this once if docs/full-supabase-setup.sql was already applied before
-- online/offline dashboard presence was added.

alter table public.profiles
add column if not exists last_seen_at timestamptz;

drop view if exists public.user_access_overview;

create view public.user_access_overview as
select
  u.id,
  u.email,
  p.full_name,
  p.avatar_url,
  p.auth_provider,
  p.requested_role,
  p.approval_status,
  p.is_active,
  p.last_seen_at,
  case
    when bool_or(ur.role = 'super_admin') then 'super_admin'::public.app_role
    when bool_or(ur.role = 'admin') then 'admin'::public.app_role
    else 'student'::public.app_role
  end as highest_role,
  coalesce(
    array_agg(ur.role order by
      case ur.role
        when 'student' then 1
        when 'admin' then 2
        when 'super_admin' then 3
      end
    ) filter (where ur.role is not null),
    array[]::public.app_role[]
  ) as all_roles,
  u.created_at,
  u.last_sign_in_at
from auth.users u
left join public.profiles p on p.id = u.id
left join public.user_roles ur on ur.user_id = u.id
group by
  u.id,
  u.email,
  p.full_name,
  p.avatar_url,
  p.auth_provider,
  p.requested_role,
  p.approval_status,
  p.is_active,
  p.last_seen_at,
  u.created_at,
  u.last_sign_in_at;

revoke all on public.user_access_overview from anon, authenticated;
