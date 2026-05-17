-- DEMO ONLY: allow the frontend selected requested_role to become the actual role.
--
-- This is useful while learning because selecting "admin" in the test UI will
-- show "admin" in public.user_roles.
--
-- Do not use this in a real production app. In production, public signup should
-- create only "student", and an existing admin/super_admin should grant higher
-- roles from a trusted backend screen.

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  selected_role public.app_role;
begin
  selected_role := case
    when new.raw_user_meta_data->>'requested_role' in ('student', 'admin', 'super_admin')
    then (new.raw_user_meta_data->>'requested_role')::public.app_role
    else 'student'::public.app_role
  end;

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
    selected_role
  )
  on conflict (id) do update
  set
    full_name = excluded.full_name,
    avatar_url = excluded.avatar_url,
    auth_provider = excluded.auth_provider,
    requested_role = excluded.requested_role;

  insert into public.user_roles (user_id, role)
  values (new.id, selected_role)
  on conflict (user_id, role) do nothing;

  if selected_role = 'admin' then
    insert into public.user_roles (user_id, role)
    values (new.id, 'student')
    on conflict (user_id, role) do nothing;
  end if;

  if selected_role = 'super_admin' then
    insert into public.user_roles (user_id, role)
    values
      (new.id, 'student'),
      (new.id, 'admin')
    on conflict (user_id, role) do nothing;
  end if;

  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row execute function public.handle_new_user();

-- Backfill existing users so their requested_role appears in user_roles too.
insert into public.user_roles (user_id, role)
select
  p.id,
  coalesce(p.requested_role, 'student'::public.app_role)
from public.profiles p
on conflict (user_id, role) do nothing;

insert into public.user_roles (user_id, role)
select p.id, 'student'::public.app_role
from public.profiles p
where p.requested_role in ('admin', 'super_admin')
on conflict (user_id, role) do nothing;

insert into public.user_roles (user_id, role)
select p.id, 'admin'::public.app_role
from public.profiles p
where p.requested_role = 'super_admin'
on conflict (user_id, role) do nothing;
