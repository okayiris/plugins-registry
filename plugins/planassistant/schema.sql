create table if not exists appointments (
  id integer primary key autoincrement,
  title text not null,
  starts text not null,            -- 'YYYY-MM-DD HH:MM', the house's own time
  ends text not null,
  place text not null default '',
  who text not null default 'me',  -- a name from people, or 'me'
  bring text not null default '',  -- who brings them there (for a child)
  pick text not null default '',   -- who picks them up
  evaluate integer not null default 0,
  note text not null default '',
  created text not null
);
create table if not exists routines (
  id integer primary key autoincrement,
  title text not null,
  who text not null default 'me',
  days text not null,              -- weekdays 0 (Monday) to 6, like '2' or '0,3'
  at text not null,                -- 'HH:MM'
  minutes integer not null default 60,
  place text not null default '',
  bring text not null default '',
  pick text not null default '',
  created text not null
);
create table if not exists tasks (
  id integer primary key autoincrement,
  title text not null,
  day text not null,               -- 'YYYY-MM-DD', or 'later'
  promised integer not null default 0,
  before text not null default '', -- the appointment it prepares, as its key
  done text not null default '',   -- when it was done
  moved integer not null default 0,
  created text not null
);
create table if not exists people (
  id integer primary key autoincrement,
  name text not null unique collate nocase,
  role text not null default 'family'  -- partner, kid, family, team
);
create table if not exists owners (
  pattern text primary key,        -- a calendar name or a word in a title, lowercase
  who text not null                -- a name, 'me' or 'family'
);
create table if not exists reviews (
  id integer primary key autoincrement,
  key text not null unique,        -- the appointment: 'YYYY-MM-DD HH:MM|title'
  title text not null,
  feeling text not null default '',
  outcome text not null default '',
  actions text not null default '',
  created text not null
);
create table if not exists places (
  address text primary key collate nocase,
  lat real,
  lon real,
  label text not null default ''
);
create table if not exists routes (
  key text primary key,
  seconds real not null,
  meters real not null,
  traffic integer not null default 0,
  at real not null
);
create table if not exists meta (
  key text primary key,
  value text not null
);
