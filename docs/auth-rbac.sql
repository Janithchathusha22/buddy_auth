-- Buddy Auth API RBAC setup for Supabase.
-- Paste this into Supabase SQL Editor and click Run.

do $$
begin
  if not exists (
    select 1
    from pg_type t
    join pg_namespace n on n.oid = t.typnamespace
    where t.typname = 'app_role'
      and n.nspname = 'public'
  ) then
    create type public.app_role as enum ('student', 'admin', 'super_admin');
  end if;
end $$;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  full_name text,
  avatar_url text,
  auth_provider text,
  requested_role public.app_role,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.profiles
add column if not exists requested_role public.app_role;

alter table public.profiles
add column if not exists avatar_url text;

alter table public.profiles
add column if not exists auth_provider text;

create table if not exists public.user_roles (
  user_id uuid not null references public.profiles(id) on delete cascade,
  role public.app_role not null,
  granted_by uuid references public.profiles(id),
  created_at timestamptz not null default now(),
  primary key (user_id, role)
);

create index if not exists user_roles_role_idx on public.user_roles(role);

alter table public.profiles enable row level security;
alter table public.user_roles enable row level security;

grant select on public.profiles to authenticated;
grant update (full_name) on public.profiles to authenticated;
grant select on public.user_roles to authenticated;

create or replace function public.touch_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists set_profiles_updated_at on public.profiles;
create trigger set_profiles_updated_at
before update on public.profiles
for each row execute function public.touch_updated_at();

create or replace function public.has_role(required_role public.app_role)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.user_roles
    where user_id = (select auth.uid())
      and role = required_role
  );
$$;

create or replace function public.has_any_role(required_roles public.app_role[])
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.user_roles
    where user_id = (select auth.uid())
      and role = any(required_roles)
  );
$$;

revoke all on function public.has_role(public.app_role) from public;
revoke all on function public.has_any_role(public.app_role[]) from public;
grant execute on function public.has_role(public.app_role) to authenticated;
grant execute on function public.has_any_role(public.app_role[]) to authenticated;

drop policy if exists "profiles_select_own_or_admin" on public.profiles;
create policy "profiles_select_own_or_admin"
on public.profiles
for select
to authenticated
using (
  (select auth.uid()) = id
  or public.has_any_role(array['admin', 'super_admin']::public.app_role[])
);

drop policy if exists "profiles_update_own_name" on public.profiles;
create policy "profiles_update_own_name"
on public.profiles
for update
to authenticated
using ((select auth.uid()) = id)
with check ((select auth.uid()) = id);

drop policy if exists "user_roles_select_own_or_admin" on public.user_roles;
create policy "user_roles_select_own_or_admin"
on public.user_roles
for select
to authenticated
using (
  (select auth.uid()) = user_id
  or public.has_any_role(array['admin', 'super_admin']::public.app_role[])
);

revoke insert, update, delete on public.user_roles from anon, authenticated;
revoke insert, delete on public.profiles from anon, authenticated;

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (
    id,
    full_name,
    avatar_url,
    auth_provider,
    requested_role
  )
  values (
    new.id,
    coalesce(new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'name'),
    coalesce(new.raw_user_meta_data->>'avatar_url', new.raw_user_meta_data->>'picture'),
    coalesce(new.raw_app_meta_data->>'provider', new.raw_app_meta_data->'providers'->>0),
    case
      when new.raw_user_meta_data->>'requested_role' in ('student', 'admin', 'super_admin')
      then (new.raw_user_meta_data->>'requested_role')::public.app_role
      else 'student'::public.app_role
    end
  )
  on conflict (id) do nothing;

  insert into public.user_roles (user_id, role)
  values (new.id, 'student')
  on conflict (user_id, role) do nothing;

  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row execute function public.handle_new_user();

insert into public.profiles (
  id,
  full_name,
  avatar_url,
  auth_provider,
  requested_role
)
select
  id,
  coalesce(raw_user_meta_data->>'full_name', raw_user_meta_data->>'name', email),
  coalesce(raw_user_meta_data->>'avatar_url', raw_user_meta_data->>'picture'),
  coalesce(raw_app_meta_data->>'provider', raw_app_meta_data->'providers'->>0),
  case
    when raw_user_meta_data->>'requested_role' in ('student', 'admin', 'super_admin')
    then (raw_user_meta_data->>'requested_role')::public.app_role
    else 'student'::public.app_role
  end
from auth.users
on conflict (id) do nothing;

update public.profiles p
set requested_role = case
  when u.raw_user_meta_data->>'requested_role' in ('student', 'admin', 'super_admin')
  then (u.raw_user_meta_data->>'requested_role')::public.app_role
  else coalesce(p.requested_role, 'student'::public.app_role)
end
from auth.users u
where u.id = p.id;

update public.profiles p
set
  full_name = coalesce(p.full_name, u.raw_user_meta_data->>'full_name', u.raw_user_meta_data->>'name', u.email),
  avatar_url = coalesce(p.avatar_url, u.raw_user_meta_data->>'avatar_url', u.raw_user_meta_data->>'picture'),
  auth_provider = coalesce(p.auth_provider, u.raw_app_meta_data->>'provider', u.raw_app_meta_data->'providers'->>0)
from auth.users u
where u.id = p.id;

insert into public.user_roles (user_id, role)
select id, 'student'::public.app_role
from auth.users
on conflict (user_id, role) do nothing;

-- Optional role seed examples.
-- Replace these emails with real users from Authentication > Users.

-- Kamal -> student + admin
-- insert into public.user_roles (user_id, role)
-- select id, role
-- from auth.users
-- cross join (
--   values
--     ('student'::public.app_role),
--     ('admin'::public.app_role)
-- ) as roles(role)
-- where email = 'kamal@example.com'
-- on conflict (user_id, role) do nothing;

-- Owner -> student + admin + super_admin
-- insert into public.user_roles (user_id, role)
-- select id, role
-- from auth.users
-- cross join (
--   values
--     ('student'::public.app_role),
--     ('admin'::public.app_role),
--     ('super_admin'::public.app_role)
-- ) as roles(role)
-- where email = 'owner@example.com'
-- on conflict (user_id, role) do nothing;
