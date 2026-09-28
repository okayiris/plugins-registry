create table if not exists habits (
  id integer primary key autoincrement,
  name text not null unique collate nocase,
  created text not null
);
create table if not exists checks (
  habit_id integer not null references habits (id) on delete cascade,
  day text not null,
  primary key (habit_id, day)
);
