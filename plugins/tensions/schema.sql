create table if not exists tensions (
  id integer primary key autoincrement,
  text text not null,
  role text not null default '',
  circle text not null default '',
  kind text not null default '',             -- '' not triaged yet, 'tactical' or 'governance'
  weight integer not null default 2,         -- 1 light, 2 clear, 3 strong
  opportunity integer not null default 0,    -- 1 when it is a chance to seize rather than a gap to close
  status text not null default 'open',       -- 'open' or 'processed'
  outcome text not null default '',          -- next-action, project, information, help, role, policy, election, dropped
  note text not null default '',
  sensed text not null,
  processed text not null default ''
);
create index if not exists tensions_status on tensions (status, kind);
