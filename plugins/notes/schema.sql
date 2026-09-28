create table if not exists notes (
  id integer primary key autoincrement,
  text text not null,
  tags text not null default '',
  pinned integer not null default 0,
  created text not null,
  updated text not null
);
create index if not exists notes_updated on notes (pinned desc, updated desc);
