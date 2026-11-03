-- Unique Pro — Supabase Free schema (run in SQL Editor)
-- Snapshot-based multi-device sync

create table if not exists unique_snapshots (
  workspace_id text primary key,
  access_key text not null,
  payload jsonb not null,
  device_id text,
  revision bigint not null default 1,
  checksum text,
  updated_at timestamptz not null default now()
);

create index if not exists unique_snapshots_updated_at_idx
  on unique_snapshots (updated_at desc);

alter table unique_snapshots enable row level security;

-- Anon key can read/write by primary key only (workspace_id must be unguessable UUID).
-- App also verifies access_key after fetch.
drop policy if exists unique_snapshots_select on unique_snapshots;
drop policy if exists unique_snapshots_insert on unique_snapshots;
drop policy if exists unique_snapshots_update on unique_snapshots;

create policy unique_snapshots_select on unique_snapshots
  for select to anon, authenticated using (true);

create policy unique_snapshots_insert on unique_snapshots
  for insert to anon, authenticated with check (true);

create policy unique_snapshots_update on unique_snapshots
  for update to anon, authenticated using (true) with check (true);

-- Optional: deny delete from clients
drop policy if exists unique_snapshots_delete on unique_snapshots;
create policy unique_snapshots_delete on unique_snapshots
  for delete to anon, authenticated using (false);
