create table if not exists projects (
  id integer primary key autoincrement,
  name text not null,
  client text not null default '',
  rate integer not null default 0,         -- cents per hour; 0 is no rate
  billable integer not null default 1,     -- new hours on this project count as billable
  active integer not null default 1,
  created text not null
);
create table if not exists entries (
  id integer primary key autoincrement,
  project_id integer not null references projects (id),
  day text not null,                       -- YYYY-MM-DD, the day the hours count for
  starts text not null default '',         -- ISO with the house's offset, when known
  ends text not null default '',
  minutes integer not null default 0,
  running integer not null default 0,      -- 1: the timer, still going
  note text not null default '',
  billable integer not null default 1,
  invoiced text not null default '',       -- the day they were put on an invoice
  invoiced_rate integer,                   -- the rate on that invoice: a later rate does not change it
  created text not null
);
create index if not exists entries_day on entries (day);
