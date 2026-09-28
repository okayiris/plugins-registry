create table if not exists expenses (
  id integer primary key autoincrement,
  day text not null,
  cents integer not null,
  category text not null,
  note text not null default '',
  created text not null
);
create index if not exists expenses_day on expenses (day);
create table if not exists budgets (
  category text primary key,
  cents integer not null
);
