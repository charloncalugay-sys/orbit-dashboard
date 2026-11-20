-- ============================================================
-- ORBIT - Supabase My Notes setup (requires orbit_auth_setup.sql)
-- Run in Supabase SQL Editor. Idempotent - safe to re-run.
--
-- My Notes were previously stored in browser localStorage, which
-- is per-browser/per-machine. This moves them server-side so notes
-- follow the signed-in Domain ID across browsers and devices.
--
-- Model (same as auth):
--   bearer token -> orbit_sessions -> domain_id (server-derived;
--   the client can never read or write another user's notes)
--   RLS deny-all on orbit_notes; anon/authenticated get EXECUTE
--   on the four RPCs below only.
-- ============================================================

create table if not exists orbit_notes (
  domain_id   text not null references orbit_directory(domain_id),
  id          text not null,
  task        text not null default '',
  priority    text not null default 'medium'
              check (priority in ('high','medium','low')),
  due         text not null default '',
  status      text not null default 'open'
              check (status in ('open','completed','archived')),
  notes       text not null default '',
  created_by  text not null default '',
  created_at  text not null default '',
  modified_by text not null default '',
  modified_at text not null default '',
  email       text not null default '',
  primary key (domain_id, id)
);

-- Resolve a bearer token to its session row; null when expired/missing.
create or replace function orbit_notes_session(p_token text)
returns orbit_sessions language sql security definer
set search_path = public, extensions as $$
  select * from orbit_sessions
   where token = p_token and expires_at > now()
   limit 1;
$$;

-- List the caller's own notes (camelCase keys, matching the app schema).
create or replace function orbit_notes_list(p_token text)
returns json language plpgsql security definer set search_path = public, extensions as $$
declare s orbit_sessions%rowtype; items json;
begin
  select * into s from orbit_notes_session(p_token);
  if not found then
    return json_build_object('ok', false, 'code', 'expired', 'error', 'Session expired.');
  end if;
  select coalesce(json_agg(json_build_object(
           'id',         n.id,
           'domain',     n.domain_id,
           'task',       n.task,
           'priority',   n.priority,
           'due',        n.due,
           'status',     n.status,
           'notes',      n.notes,
           'createdBy',  n.created_by,
           'createdAt',  n.created_at,
           'modifiedBy', n.modified_by,
           'modifiedAt', n.modified_at,
           'email',      n.email
         ) order by n.created_at), '[]'::json)
    into items
    from orbit_notes n
   where n.domain_id = s.domain_id;
  return json_build_object('ok', true, 'notes', items);
end $$;

-- Upsert one note for the caller. p_note carries the camelCase task
-- object the app already uses; server stamps domain_id from the session.
create or replace function orbit_notes_save(p_token text, p_note jsonb)
returns json language plpgsql security definer set search_path = public, extensions as $$
declare s orbit_sessions%rowtype; nid text;
begin
  select * into s from orbit_notes_session(p_token);
  if not found then
    return json_build_object('ok', false, 'code', 'expired', 'error', 'Session expired.');
  end if;
  nid := nullif(trim(coalesce(p_note->>'id', '')), '');
  if nid is null then
    return json_build_object('ok', false, 'error', 'Note id is required.');
  end if;
  insert into orbit_notes
    (domain_id, id, task, priority, due, status, notes,
     created_by, created_at, modified_by, modified_at, email)
  values
    (s.domain_id, nid,
     coalesce(p_note->>'task', ''),
     case when p_note->>'priority' in ('high','medium','low')
          then p_note->>'priority' else 'medium' end,
     coalesce(p_note->>'due', ''),
     case when p_note->>'status' in ('open','completed','archived')
          then p_note->>'status' else 'open' end,
     coalesce(p_note->>'notes', ''),
     coalesce(p_note->>'createdBy', ''),
     coalesce(p_note->>'createdAt', ''),
     coalesce(p_note->>'modifiedBy', ''),
     coalesce(p_note->>'modifiedAt', ''),
     coalesce(p_note->>'email', ''))
  on conflict (domain_id, id) do update set
    task        = excluded.task,
    priority    = excluded.priority,
    due         = excluded.due,
    status      = excluded.status,
    notes       = excluded.notes,
    modified_by = excluded.modified_by,
    modified_at = excluded.modified_at;
  return json_build_object('ok', true);
end $$;

-- Delete one of the caller's notes.
create or replace function orbit_notes_delete(p_token text, p_id text)
returns json language plpgsql security definer set search_path = public, extensions as $$
declare s orbit_sessions%rowtype;
begin
  select * into s from orbit_notes_session(p_token);
  if not found then
    return json_build_object('ok', false, 'code', 'expired', 'error', 'Session expired.');
  end if;
  delete from orbit_notes where domain_id = s.domain_id and id = p_id;
  return json_build_object('ok', true);
end $$;

-- One-time migration helper: bulk-upsert a browser's local notes.
-- Local-only ids (not yet on the server) are inserted; existing ids
-- are left untouched (server copy wins).
create or replace function orbit_notes_import(p_token text, p_notes jsonb)
returns json language plpgsql security definer set search_path = public, extensions as $$
declare s orbit_sessions%rowtype; n jsonb; added int := 0;
begin
  select * into s from orbit_notes_session(p_token);
  if not found then
    return json_build_object('ok', false, 'code', 'expired', 'error', 'Session expired.');
  end if;
  if jsonb_typeof(p_notes) <> 'array' then
    return json_build_object('ok', false, 'error', 'p_notes must be a JSON array.');
  end if;
  for n in select * from jsonb_array_elements(p_notes) loop
    if nullif(trim(coalesce(n->>'id', '')), '') is null
       or nullif(trim(coalesce(n->>'task', '')), '') is null then
      continue;
    end if;
    insert into orbit_notes
      (domain_id, id, task, priority, due, status, notes,
       created_by, created_at, modified_by, modified_at, email)
    values
      (s.domain_id, n->>'id',
       coalesce(n->>'task', ''),
       case when n->>'priority' in ('high','medium','low')
            then n->>'priority' else 'medium' end,
       coalesce(n->>'due', ''),
       case when n->>'status' in ('open','completed','archived')
            then n->>'status' else 'open' end,
       coalesce(n->>'notes', ''),
       coalesce(n->>'createdBy', ''),
       coalesce(n->>'createdAt', ''),
       coalesce(n->>'modifiedBy', ''),
       coalesce(n->>'modifiedAt', ''),
       coalesce(n->>'email', ''))
    on conflict (domain_id, id) do nothing;
    if found then added := added + 1; end if;
  end loop;
  return json_build_object('ok', true, 'imported', added);
end $$;

-- ── Lockdown + grants ────────────────────────────────────────
alter table orbit_notes enable row level security;

revoke all on orbit_notes from anon, authenticated;
revoke all on function orbit_notes_session(text) from anon, authenticated;

grant execute on function orbit_notes_list(text)            to anon, authenticated;
grant execute on function orbit_notes_save(text, jsonb)     to anon, authenticated;
grant execute on function orbit_notes_delete(text, text)    to anon, authenticated;
grant execute on function orbit_notes_import(text, jsonb)   to anon, authenticated;
-- orbit_notes_session intentionally NOT granted - internal helper only.
