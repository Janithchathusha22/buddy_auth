-- =========================================================
-- Buddy Project Full Supabase SQL
-- Supabase Auth + PostgreSQL RBAC + LMS tables
-- Roles: student, admin, super_admin
-- Owner super admin email: danu@absolx.com
--
-- Passwords are not stored here. Supabase Auth owns passwords.
-- Paste this whole file into Supabase SQL Editor and run it.
-- =========================================================

create extension if not exists pgcrypto with schema extensions;

-- Remove old generated objects that may depend on public.app_role.
drop view if exists public.user_access_overview;

drop function if exists public.set_user_active_by_email(text, boolean) cascade;
drop function if exists public.is_approved_active(uuid) cascade;
drop function if exists public.can_manage_content() cascade;
drop function if exists public.can_manage_course(uuid) cascade;
drop function if exists public.can_view_course(uuid) cascade;
drop function if exists public.can_edit_course(uuid) cascade;

do $$
begin
  if exists (
    select 1
    from pg_type t
    join pg_namespace n on n.oid = t.typnamespace
    where t.typname = 'app_role'
      and n.nspname = 'public'
  ) then
    execute 'drop function if exists public.approve_user_by_email(text, public.app_role) cascade';
    execute 'drop function if exists public.has_role(public.app_role) cascade';
    execute 'drop function if exists public.has_any_role(public.app_role[]) cascade';
  end if;
end $$;

-- If a previous test added a teacher enum value, rebuild app_role safely.
do $$
begin
  if to_regclass('public.user_roles') is not null then
    delete from public.user_roles
    where role::text = 'teacher';

    alter table public.user_roles
      alter column role type text
      using role::text;
  end if;

  if to_regclass('public.profiles') is not null then
    alter table public.profiles
      alter column requested_role drop default;

    alter table public.profiles
      alter column requested_role type text
      using case
        when requested_role::text = 'teacher' then 'admin'
        when requested_role::text in ('student', 'admin', 'super_admin') then requested_role::text
        else 'student'
      end;
  end if;
end $$;

drop type if exists public.app_role;
create type public.app_role as enum ('student', 'admin', 'super_admin');

do $$
begin
  if to_regclass('public.user_roles') is not null then
    alter table public.user_roles
      alter column role type public.app_role
      using role::public.app_role;
  end if;

  if to_regclass('public.profiles') is not null then
    alter table public.profiles
      alter column requested_role type public.app_role
      using requested_role::public.app_role;

    alter table public.profiles
      alter column requested_role set default 'student'::public.app_role;
  end if;
end $$;

do $$
begin
  if not exists (
    select 1
    from pg_type t
    join pg_namespace n on n.oid = t.typnamespace
    where t.typname = 'approval_status'
      and n.nspname = 'public'
  ) then
    create type public.approval_status as enum (
      'pending',
      'approved',
      'rejected',
      'suspended'
    );
  end if;
end $$;

do $$
begin
  if not exists (
    select 1
    from pg_type t
    join pg_namespace n on n.oid = t.typnamespace
    where t.typname = 'course_status'
      and n.nspname = 'public'
  ) then
    create type public.course_status as enum ('draft', 'published', 'archived');
  end if;
end $$;

do $$
begin
  if not exists (
    select 1
    from pg_type t
    join pg_namespace n on n.oid = t.typnamespace
    where t.typname = 'lesson_progress_status'
      and n.nspname = 'public'
  ) then
    create type public.lesson_progress_status as enum (
      'not_started',
      'in_progress',
      'completed'
    );
  end if;
end $$;

-- =========================================================
-- 1. Auth profile and role tables
-- =========================================================

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  full_name text,
  avatar_url text,
  auth_provider text,
  requested_role public.app_role default 'student',
  approval_status public.approval_status not null default 'pending',
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.profiles add column if not exists full_name text;
alter table public.profiles add column if not exists avatar_url text;
alter table public.profiles add column if not exists auth_provider text;
alter table public.profiles add column if not exists requested_role public.app_role default 'student';
alter table public.profiles add column if not exists approval_status public.approval_status not null default 'pending';
alter table public.profiles add column if not exists is_active boolean not null default true;
alter table public.profiles add column if not exists created_at timestamptz not null default now();
alter table public.profiles add column if not exists updated_at timestamptz not null default now();

create table if not exists public.user_roles (
  user_id uuid not null references public.profiles(id) on delete cascade,
  role public.app_role not null,
  granted_by uuid references public.profiles(id),
  created_at timestamptz not null default now(),
  primary key (user_id, role)
);

create index if not exists user_roles_role_idx on public.user_roles(role);

-- =========================================================
-- 2. Shared helper functions
-- =========================================================

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
    where user_id = auth.uid()
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
    where user_id = auth.uid()
      and role = any(required_roles)
  );
$$;

create or replace function public.is_approved_active(target_user_id uuid default auth.uid())
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.profiles
    where id = target_user_id
      and approval_status = 'approved'
      and is_active = true
  );
$$;

revoke all on function public.has_role(public.app_role) from public;
revoke all on function public.has_any_role(public.app_role[]) from public;
revoke all on function public.is_approved_active(uuid) from public;

grant execute on function public.has_role(public.app_role) to authenticated;
grant execute on function public.has_any_role(public.app_role[]) to authenticated;
grant execute on function public.is_approved_active(uuid) to authenticated;

-- =========================================================
-- 3. Signup trigger
-- Any normal signup starts pending + actual role student only.
-- Owner email gets approved + student/admin/super_admin automatically.
-- =========================================================

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  requested public.app_role;
begin
  requested := case
    when new.raw_user_meta_data->>'requested_role' in ('student', 'admin', 'super_admin')
    then (new.raw_user_meta_data->>'requested_role')::public.app_role
    else 'student'::public.app_role
  end;

  if lower(new.email) = 'danu@absolx.com' then
    requested := 'super_admin'::public.app_role;
  end if;

  insert into public.profiles (
    id,
    full_name,
    avatar_url,
    auth_provider,
    requested_role,
    approval_status,
    is_active
  )
  values (
    new.id,
    coalesce(new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'name', new.email),
    coalesce(new.raw_user_meta_data->>'avatar_url', new.raw_user_meta_data->>'picture'),
    coalesce(new.raw_app_meta_data->>'provider', new.raw_app_meta_data->'providers'->>0, 'email'),
    requested,
    case
      when lower(new.email) = 'danu@absolx.com' then 'approved'::public.approval_status
      else 'pending'::public.approval_status
    end,
    true
  )
  on conflict (id) do update set
    full_name = coalesce(public.profiles.full_name, excluded.full_name),
    avatar_url = coalesce(public.profiles.avatar_url, excluded.avatar_url),
    auth_provider = coalesce(public.profiles.auth_provider, excluded.auth_provider),
    requested_role = excluded.requested_role,
    approval_status = case
      when lower(new.email) = 'danu@absolx.com' then 'approved'::public.approval_status
      else public.profiles.approval_status
    end,
    is_active = case
      when lower(new.email) = 'danu@absolx.com' then true
      else public.profiles.is_active
    end,
    updated_at = now();

  insert into public.user_roles (user_id, role)
  values (new.id, 'student'::public.app_role)
  on conflict (user_id, role) do nothing;

  if lower(new.email) = 'danu@absolx.com' then
    insert into public.user_roles (user_id, role)
    values
      (new.id, 'student'::public.app_role),
      (new.id, 'admin'::public.app_role),
      (new.id, 'super_admin'::public.app_role)
    on conflict (user_id, role) do nothing;
  end if;

  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row execute function public.handle_new_user();

-- =========================================================
-- 4. Backfill existing Supabase Auth users
-- =========================================================

insert into public.profiles (
  id,
  full_name,
  avatar_url,
  auth_provider,
  requested_role,
  approval_status,
  is_active
)
select
  id,
  coalesce(raw_user_meta_data->>'full_name', raw_user_meta_data->>'name', email),
  coalesce(raw_user_meta_data->>'avatar_url', raw_user_meta_data->>'picture'),
  coalesce(raw_app_meta_data->>'provider', raw_app_meta_data->'providers'->>0, 'email'),
  case
    when lower(email) = 'danu@absolx.com' then 'super_admin'::public.app_role
    when raw_user_meta_data->>'requested_role' in ('student', 'admin', 'super_admin')
    then (raw_user_meta_data->>'requested_role')::public.app_role
    else 'student'::public.app_role
  end,
  case
    when lower(email) = 'danu@absolx.com' then 'approved'::public.approval_status
    else 'pending'::public.approval_status
  end,
  true
from auth.users
on conflict (id) do nothing;

insert into public.user_roles (user_id, role)
select id, 'student'::public.app_role
from auth.users
on conflict (user_id, role) do nothing;

insert into public.user_roles (user_id, role)
select u.id, r.role
from auth.users u
cross join (
  values
    ('student'::public.app_role),
    ('admin'::public.app_role),
    ('super_admin'::public.app_role)
) as r(role)
where lower(u.email) = 'danu@absolx.com'
on conflict (user_id, role) do nothing;

update public.profiles p
set
  requested_role = 'super_admin',
  approval_status = 'approved',
  is_active = true
from auth.users u
where u.id = p.id
  and lower(u.email) = 'danu@absolx.com';

-- =========================================================
-- 5. LMS tables
-- =========================================================

drop table if exists public.course_teachers cascade;
drop table if exists public.course_admins cascade;

create table if not exists public.courses (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  description text,
  status public.course_status not null default 'draft',
  created_by uuid references public.profiles(id) default auth.uid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.course_students (
  course_id uuid not null references public.courses(id) on delete cascade,
  student_id uuid not null references public.profiles(id) on delete cascade,
  assigned_by uuid references public.profiles(id) default auth.uid(),
  assigned_at timestamptz not null default now(),
  primary key (course_id, student_id)
);

create table if not exists public.lessons (
  id uuid primary key default gen_random_uuid(),
  course_id uuid not null references public.courses(id) on delete cascade,
  title text not null,
  content text,
  sort_order integer not null default 0,
  is_published boolean not null default false,
  created_by uuid references public.profiles(id) default auth.uid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.quizzes (
  id uuid primary key default gen_random_uuid(),
  lesson_id uuid not null references public.lessons(id) on delete cascade,
  title text not null,
  instructions text,
  max_score numeric(8, 2) not null default 100,
  created_by uuid references public.profiles(id) default auth.uid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.lesson_progress (
  student_id uuid not null references public.profiles(id) on delete cascade,
  lesson_id uuid not null references public.lessons(id) on delete cascade,
  status public.lesson_progress_status not null default 'not_started',
  progress_percent integer not null default 0 check (progress_percent between 0 and 100),
  completed_at timestamptz,
  updated_at timestamptz not null default now(),
  primary key (student_id, lesson_id)
);

create table if not exists public.quiz_attempts (
  id uuid primary key default gen_random_uuid(),
  quiz_id uuid not null references public.quizzes(id) on delete cascade,
  student_id uuid not null references public.profiles(id) on delete cascade,
  score numeric(8, 2),
  answers jsonb not null default '{}'::jsonb,
  submitted_at timestamptz not null default now()
);

alter table public.courses alter column created_by set default auth.uid();
alter table public.course_students alter column assigned_by set default auth.uid();
alter table public.lessons alter column created_by set default auth.uid();
alter table public.quizzes alter column created_by set default auth.uid();

create index if not exists courses_status_idx on public.courses(status);
create index if not exists course_students_student_id_idx on public.course_students(student_id);
create index if not exists lessons_course_id_idx on public.lessons(course_id);
create index if not exists quizzes_lesson_id_idx on public.quizzes(lesson_id);
create index if not exists lesson_progress_lesson_id_idx on public.lesson_progress(lesson_id);
create index if not exists quiz_attempts_student_id_idx on public.quiz_attempts(student_id);

drop trigger if exists set_courses_updated_at on public.courses;
create trigger set_courses_updated_at
before update on public.courses
for each row execute function public.touch_updated_at();

drop trigger if exists set_lessons_updated_at on public.lessons;
create trigger set_lessons_updated_at
before update on public.lessons
for each row execute function public.touch_updated_at();

drop trigger if exists set_quizzes_updated_at on public.quizzes;
create trigger set_quizzes_updated_at
before update on public.quizzes
for each row execute function public.touch_updated_at();

drop trigger if exists set_lesson_progress_updated_at on public.lesson_progress;
create trigger set_lesson_progress_updated_at
before update on public.lesson_progress
for each row execute function public.touch_updated_at();

-- =========================================================
-- 6. LMS permission helpers
-- =========================================================

create or replace function public.can_manage_content()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select public.is_approved_active()
    and public.has_any_role(array['admin', 'super_admin']::public.app_role[]);
$$;

create or replace function public.can_view_course(target_course_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select public.is_approved_active()
    and (
      public.has_any_role(array['admin', 'super_admin']::public.app_role[])
      or exists (
        select 1
        from public.course_students
        where course_id = target_course_id
          and student_id = auth.uid()
      )
    );
$$;

revoke all on function public.can_manage_content() from public;
revoke all on function public.can_view_course(uuid) from public;

grant execute on function public.can_manage_content() to authenticated;
grant execute on function public.can_view_course(uuid) to authenticated;

-- =========================================================
-- 7. RLS + grants
-- =========================================================

alter table public.profiles enable row level security;
alter table public.user_roles enable row level security;
alter table public.courses enable row level security;
alter table public.course_students enable row level security;
alter table public.lessons enable row level security;
alter table public.quizzes enable row level security;
alter table public.lesson_progress enable row level security;
alter table public.quiz_attempts enable row level security;

grant select on public.profiles to authenticated;
grant update (full_name, avatar_url) on public.profiles to authenticated;
grant select on public.user_roles to authenticated;

grant select, insert, update, delete on public.courses to authenticated;
grant select, insert, update, delete on public.course_students to authenticated;
grant select, insert, update, delete on public.lessons to authenticated;
grant select, insert, update, delete on public.quizzes to authenticated;
grant select, insert, update on public.lesson_progress to authenticated;
grant select, insert on public.quiz_attempts to authenticated;

revoke insert, update, delete on public.user_roles from anon, authenticated;
revoke insert, delete on public.profiles from anon, authenticated;

-- =========================================================
-- 8. RLS policies: auth tables
-- =========================================================

drop policy if exists "profiles_select_own_or_staff" on public.profiles;
create policy "profiles_select_own_or_staff"
on public.profiles
for select
to authenticated
using (
  auth.uid() = id
  or (
    public.is_approved_active()
    and public.has_any_role(array['admin', 'super_admin']::public.app_role[])
  )
);

drop policy if exists "profiles_update_own_basic_fields" on public.profiles;
create policy "profiles_update_own_basic_fields"
on public.profiles
for update
to authenticated
using (auth.uid() = id)
with check (auth.uid() = id);

drop policy if exists "user_roles_select_own_or_super_admin" on public.user_roles;
create policy "user_roles_select_own_or_super_admin"
on public.user_roles
for select
to authenticated
using (
  auth.uid() = user_id
  or (
    public.is_approved_active()
    and public.has_role('super_admin')
  )
);

-- =========================================================
-- 9. RLS policies: LMS tables
-- =========================================================

drop policy if exists "courses_select_by_access" on public.courses;
create policy "courses_select_by_access"
on public.courses
for select
to authenticated
using (public.can_view_course(id));

drop policy if exists "courses_insert_admin_super_admin" on public.courses;
create policy "courses_insert_admin_super_admin"
on public.courses
for insert
to authenticated
with check (public.can_manage_content());

drop policy if exists "courses_update_admin_super_admin" on public.courses;
create policy "courses_update_admin_super_admin"
on public.courses
for update
to authenticated
using (public.can_manage_content())
with check (public.can_manage_content());

drop policy if exists "courses_delete_admin_super_admin" on public.courses;
create policy "courses_delete_admin_super_admin"
on public.courses
for delete
to authenticated
using (public.can_manage_content());

drop policy if exists "course_students_select_related" on public.course_students;
create policy "course_students_select_related"
on public.course_students
for select
to authenticated
using (
  student_id = auth.uid()
  or public.can_manage_content()
);

drop policy if exists "course_students_manage_admin_super_admin" on public.course_students;
create policy "course_students_manage_admin_super_admin"
on public.course_students
for all
to authenticated
using (public.can_manage_content())
with check (public.can_manage_content());

drop policy if exists "lessons_select_course_members" on public.lessons;
create policy "lessons_select_course_members"
on public.lessons
for select
to authenticated
using (
  public.can_manage_content()
  or (
    is_published = true
    and public.can_view_course(course_id)
  )
);

drop policy if exists "lessons_manage_admin_super_admin" on public.lessons;
create policy "lessons_manage_admin_super_admin"
on public.lessons
for all
to authenticated
using (public.can_manage_content())
with check (public.can_manage_content());

drop policy if exists "quizzes_select_course_members" on public.quizzes;
create policy "quizzes_select_course_members"
on public.quizzes
for select
to authenticated
using (
  public.can_manage_content()
  or exists (
    select 1
    from public.lessons l
    where l.id = lesson_id
      and l.is_published = true
      and public.can_view_course(l.course_id)
  )
);

drop policy if exists "quizzes_manage_admin_super_admin" on public.quizzes;
create policy "quizzes_manage_admin_super_admin"
on public.quizzes
for all
to authenticated
using (public.can_manage_content())
with check (public.can_manage_content());

drop policy if exists "lesson_progress_select_related" on public.lesson_progress;
create policy "lesson_progress_select_related"
on public.lesson_progress
for select
to authenticated
using (
  student_id = auth.uid()
  or public.can_manage_content()
);

drop policy if exists "lesson_progress_student_insert_own" on public.lesson_progress;
create policy "lesson_progress_student_insert_own"
on public.lesson_progress
for insert
to authenticated
with check (
  student_id = auth.uid()
  and exists (
    select 1
    from public.lessons l
    where l.id = lesson_id
      and l.is_published = true
      and public.can_view_course(l.course_id)
  )
);

drop policy if exists "lesson_progress_student_update_own" on public.lesson_progress;
create policy "lesson_progress_student_update_own"
on public.lesson_progress
for update
to authenticated
using (student_id = auth.uid())
with check (student_id = auth.uid());

drop policy if exists "quiz_attempts_select_related" on public.quiz_attempts;
create policy "quiz_attempts_select_related"
on public.quiz_attempts
for select
to authenticated
using (
  student_id = auth.uid()
  or public.can_manage_content()
);

drop policy if exists "quiz_attempts_student_insert_own" on public.quiz_attempts;
create policy "quiz_attempts_student_insert_own"
on public.quiz_attempts
for insert
to authenticated
with check (
  student_id = auth.uid()
  and exists (
    select 1
    from public.quizzes q
    join public.lessons l on l.id = q.lesson_id
    where q.id = quiz_id
      and l.is_published = true
      and public.can_view_course(l.course_id)
  )
);

-- =========================================================
-- 10. SQL Editor helper functions
-- These are for the project owner using Supabase SQL Editor.
-- App users cannot execute them directly.
-- =========================================================

create or replace function public.approve_user_by_email(
  target_email text,
  approved_role public.app_role
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  target_user_id uuid;
begin
  select id
  into target_user_id
  from auth.users
  where lower(email) = lower(target_email)
  limit 1;

  if target_user_id is null then
    raise exception 'No Supabase auth user found for email %', target_email;
  end if;

  update public.profiles
  set
    approval_status = 'approved',
    is_active = true,
    requested_role = approved_role
  where id = target_user_id;

  delete from public.user_roles
  where user_id = target_user_id;

  insert into public.user_roles (user_id, role)
  values (target_user_id, 'student'::public.app_role)
  on conflict (user_id, role) do nothing;

  if approved_role in ('admin'::public.app_role, 'super_admin'::public.app_role) then
    insert into public.user_roles (user_id, role)
    values (target_user_id, 'admin'::public.app_role)
    on conflict (user_id, role) do nothing;
  end if;

  if approved_role = 'super_admin'::public.app_role then
    insert into public.user_roles (user_id, role)
    values (target_user_id, 'super_admin'::public.app_role)
    on conflict (user_id, role) do nothing;
  end if;
end;
$$;

create or replace function public.set_user_active_by_email(
  target_email text,
  active boolean
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  update public.profiles p
  set
    is_active = active,
    approval_status = case
      when active then 'approved'::public.approval_status
      else 'suspended'::public.approval_status
    end
  from auth.users u
  where u.id = p.id
    and lower(u.email) = lower(target_email);
end;
$$;

revoke all on function public.approve_user_by_email(text, public.app_role) from public;
revoke all on function public.set_user_active_by_email(text, boolean) from public;

-- =========================================================
-- 11. SQL Editor overview view
-- =========================================================

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
  u.created_at,
  u.last_sign_in_at;

revoke all on public.user_access_overview from anon, authenticated;

-- Useful SQL Editor checks:
-- select * from public.user_access_overview order by created_at desc;
-- select public.approve_user_by_email('student@example.com', 'student');
-- select public.approve_user_by_email('admin@example.com', 'admin');
-- select public.approve_user_by_email('other-owner@example.com', 'super_admin');
-- select public.set_user_active_by_email('student@example.com', false);

-- =========================================================
-- DONE
-- =========================================================
