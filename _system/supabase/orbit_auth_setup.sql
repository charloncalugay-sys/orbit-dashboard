-- ============================================================
-- ORBIT - Supabase auth setup (mirrors TEMPUS model)
-- Run in Supabase SQL Editor. Idempotent - safe to re-run.
--
-- Model:
--   publishable key -> PostgREST RPC only
--   bcrypt passwords (pgcrypto.crypt) on orbit_directory
--   server-side sessions on orbit_sessions (12h bearer tokens)
--   RLS deny-all on tables; anon/authenticated get EXECUTE on
--   the safe RPCs only.
--
-- Flow (mirrors TEMPUS 06_passwords.sql):
--   1. signIn(domain) -> user has no password_hash -> needSetup
--   2. UI asks for team passcode + new personal password
--      -> orbit_setup_password -> session issued
--   3. Thereafter domain + personal password -> orbit_login
-- ============================================================

create extension if not exists pgcrypto;

-- ── Tables ───────────────────────────────────────────────────
create table if not exists orbit_directory (
  domain_id     text primary key,
  name          text not null,
  role          text not null default 'leadership'
                check (role in ('leadership','admin')),
  email         text,
  manager       text,
  password_hash text
);

create table if not exists orbit_sessions (
  token      text primary key default encode(gen_random_bytes(32),'hex'),
  domain_id  text not null references orbit_directory(domain_id),
  role       text not null,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default now() + interval '12 hours'
);
create index if not exists ix_orbit_sessions_exp on orbit_sessions (expires_at);

create table if not exists orbit_settings (
  key   text primary key,
  value text
);

insert into orbit_settings (key, value) values
  ('schema_version', '1'),
  ('leadership_passcode', null)   -- set via orbit_set_passcode()
on conflict (key) do nothing;

-- ── RPCs ─────────────────────────────────────────────────────

-- Sign-in: domain + personal password.
-- needSetup    -> first-time leader: no password_hash yet
-- needPasscode -> password wrong or missing
create or replace function orbit_login(p_domain text, p_passcode text default null)
returns json language plpgsql security definer set search_path = public, extensions as $$
declare
  d   orbit_directory%rowtype;
  tok text;
begin
  select * into d from orbit_directory where upper(domain_id) = upper(trim(p_domain));
  if not found then
    return json_build_object('ok', false, 'code', 'unknown_user',
                             'error', 'Domain ID not found in the ORBIT Leadership roster.');
  end if;
  if d.password_hash is null then
    return json_build_object('ok', false, 'code', 'setup', 'needSetup', true,
      'error', 'First-time sign-in: set your personal password.');
  end if;
  if p_passcode is null or crypt(p_passcode, d.password_hash) <> d.password_hash then
    return json_build_object('ok', false, 'code', 'need_passcode',
      'error', 'Incorrect or missing password.', 'needPasscode', true);
  end if;
  delete from orbit_sessions where expires_at < now();
  insert into orbit_sessions (domain_id, role) values (d.domain_id, d.role)
    returning token into tok;
  return json_build_object(
    'ok', true, 'token', tok,
    'profile', json_build_object(
      'id', d.domain_id, 'name', d.name, 'role', d.role,
      'email', d.email, 'manager', d.manager));
end $$;

-- First-time setup: prove team membership once via the shared team
-- passcode, then set a personal password and get a session.
create or replace function orbit_setup_password(p_domain text, p_bootstrap text,
        p_new_password text)
returns json language plpgsql security definer set search_path = public, extensions as $$
declare
  d orbit_directory%rowtype; shared text; tok text;
begin
  select * into d from orbit_directory where upper(domain_id) = upper(trim(p_domain));
  if not found then
    return json_build_object('ok', false, 'error', 'Unknown Domain ID.'); end if;
  if d.password_hash is not null then
    return json_build_object('ok', false, 'error', 'Password already set - sign in normally.'); end if;
  select value into shared from orbit_settings where key = 'leadership_passcode';
  if shared is null then
    return json_build_object('ok', false, 'error',
      'Onboarding passcode not configured yet - ask your admin.'); end if;
  if p_bootstrap is null or crypt(p_bootstrap, shared) <> shared then
    return json_build_object('ok', false, 'error', 'Incorrect team passcode.'); end if;
  if p_new_password is null or length(p_new_password) < 8 then
    return json_build_object('ok', false, 'error', 'Password must be at least 8 characters.'); end if;
  update orbit_directory set password_hash = crypt(p_new_password, gen_salt('bf'))
    where domain_id = d.domain_id;
  delete from orbit_sessions where expires_at < now();
  insert into orbit_sessions (domain_id, role) values (d.domain_id, d.role)
    returning token into tok;
  return json_build_object(
    'ok', true, 'token', tok,
    'profile', json_build_object(
      'id', d.domain_id, 'name', d.name, 'role', d.role,
      'email', d.email, 'manager', d.manager));
end $$;

-- Validate a bearer token -> session profile.
create or replace function orbit_session(p_token text)
returns json language plpgsql security definer set search_path = public, extensions as $$
declare s orbit_sessions%rowtype; d orbit_directory%rowtype;
begin
  select * into s from orbit_sessions where token = p_token and expires_at > now();
  if not found then
    return json_build_object('ok', false, 'code', 'expired', 'error', 'Session expired.');
  end if;
  select * into d from orbit_directory where domain_id = s.domain_id;
  return json_build_object(
    'ok', true,
    'profile', json_build_object(
      'id', d.domain_id, 'name', d.name, 'role', d.role,
      'email', d.email, 'manager', d.manager));
end $$;

create or replace function orbit_logout(p_token text)
returns json language plpgsql security definer set search_path = public, extensions as $$
begin
  delete from orbit_sessions where token = p_token;
  return json_build_object('ok', true);
end $$;

-- Change own password (requires valid session).
create or replace function orbit_change_password(p_token text, p_current text, p_new text)
returns json language plpgsql security definer set search_path = public, extensions as $$
declare s orbit_sessions%rowtype; d orbit_directory%rowtype;
begin
  select * into s from orbit_sessions where token = p_token and expires_at > now();
  if not found then
    return json_build_object('ok', false, 'code', 'expired', 'error', 'Session expired.'); end if;
  select * into d from orbit_directory where domain_id = s.domain_id;
  if d.password_hash is not null
     and (p_current is null or crypt(p_current, d.password_hash) <> d.password_hash) then
    return json_build_object('ok', false, 'error', 'Current password is incorrect.'); end if;
  if p_new is null or length(p_new) < 8 then
    return json_build_object('ok', false, 'error', 'Password must be at least 8 characters.'); end if;
  update orbit_directory set password_hash = crypt(p_new, gen_salt('bf'))
    where domain_id = d.domain_id;
  return json_build_object('ok', true);
end $$;

-- Set the team onboarding passcode (stores bcrypt hash).
-- ADMIN/MAINTENANCE ONLY - not granted to anon; run via SQL editor
-- or service key.
create or replace function orbit_set_passcode(p_new_passcode text)
returns json language plpgsql security definer set search_path = public, extensions as $$
begin
  if p_new_passcode is null or length(p_new_passcode) < 12 then
    return json_build_object('ok', false, 'error', 'Passcode must be >=12 chars.');
  end if;
  insert into orbit_settings (key, value) values
    ('leadership_passcode', crypt(p_new_passcode, gen_salt('bf')))
  on conflict (key) do update set value = excluded.value;
  return json_build_object('ok', true);
end $$;

-- ── Directory seed: D_LEADERSHIP (ORBIT_Leadership.xlsx, 2026-11-19) ──
insert into orbit_directory (domain_id, name, role, email, manager) values
  ('AM36347','Borjal, Rey And','leadership','ReyAnd.Borjal@carelon.com','Cheng, John'),
  ('AL01683','Publico, Chernobyl','leadership','Chernobyl.Publico@carelon.com','Dantes, Ma. Rowena'),
  ('AG52173','Alcantara, John Patrick','leadership','JohnPatrick.Alcantara@carelon.com','Dantes, Ma. Rowena'),
  ('AM12859','Besa, Romelyn','leadership','Romelyn.Besa@carelon.com','Cheng, John'),
  ('AH35045','Abalos, Bony','leadership','BonyJr.Abalos@carelon.com','Dantes, Ma. Rowena'),
  ('AG55197','Natividad, Elaine','leadership','Elaine.Natividad@carelon.com','Cheng, John'),
  ('AH19422','Nido, Brent','leadership','Brent.Nido@carelon.com','Dantes, Ma. Rowena'),
  ('AG52450','Vergara, Mickee','leadership','Mickee.Vergara@carelon.com','Dantes, Ma. Rowena'),
  ('AG84583','Alfonso, Clarisa','leadership','Clarisa.Alfonso@carelon.com','Dantes, Ma. Rowena'),
  ('AM42550','RUTOR, JENNIFER','leadership','JENNIFER.RUTOR@carelon.com','Dantes, Ma. Rowena'),
  ('AG49752','Cabalida, Lyndell','leadership','Lyndell.Cabalida@carelon.com','Dantes, Ma. Rowena'),
  ('AG49229','Costiniano, Rachel Ann','leadership','RachelAnn.Babagay@carelon.com','Cheng, John'),
  ('AH19689','Quijano, Katherine','leadership','Katherine.Pantas@carelon.com','Cheng, John'),
  ('AM36967','Cheng, John','leadership','JOHN.CHENG@carelon.com','Sanchez, Michelle'),
  ('AG54148','Dantes, Ma. Rowena','leadership','Ma.Rowena.Dantes@carelon.com','Sanchez, Michelle'),
  ('AL70683','Calugay, Charlon','admin','Charlon.Calugay@carelon.com','Alfonso, Clarisa'),
  ('AH01906','Cabunyag, Jocelyn','admin','Jocelyn.Cabunyag@carelon.com','Publico, Chernobyl'),
  ('AG89420','Caubalejo, John Eric','admin','JohnEric.Caubalejo@carelon.com','Publico, Chernobyl')
on conflict (domain_id) do update
  set name = excluded.name, role = excluded.role,
      email = excluded.email, manager = excluded.manager;

-- ── Lockdown + grants ────────────────────────────────────────
alter table orbit_directory enable row level security;
alter table orbit_sessions  enable row level security;
alter table orbit_settings  enable row level security;

revoke all on all tables in schema public from anon, authenticated;
revoke all on all functions in schema public from anon, authenticated;

grant execute on function orbit_login(text, text)            to anon, authenticated;
grant execute on function orbit_session(text)                to anon, authenticated;
grant execute on function orbit_logout(text)                 to anon, authenticated;
grant execute on function orbit_setup_password(text, text, text) to anon, authenticated;
grant execute on function orbit_change_password(text, text, text) to anon, authenticated;
-- orbit_set_passcode intentionally NOT granted - run via SQL editor:
--   select orbit_set_passcode('your-long-team-passcode');
