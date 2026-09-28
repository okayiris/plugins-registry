create table if not exists lists (
  id integer primary key autoincrement,
  name text not null unique collate nocase,
  created text not null,
  updated text not null
);
create table if not exists items (
  id integer primary key autoincrement,
  list_id integer not null references lists (id) on delete cascade,
  text text not null,
  done integer not null default 0,
  position integer not null default 0
);
create index if not exists items_list on items (list_id, position);
