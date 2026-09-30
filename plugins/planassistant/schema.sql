create table if not exists tasks (
  id integer primary key autoincrement,
  title text not null,
  day text not null,               -- 'YYYY-MM-DD', or 'later'
  promised integer not null default 0,
  before text not null default '', -- the appointment it prepares, as 'YYYY-MM-DD HH:MM|title'
  done text not null default '',   -- when it was done
  moved integer not null default 0,
  created text not null
);
create table if not exists people (
  id integer primary key autoincrement,
  name text not null unique collate nocase,
  role text not null default 'family'  -- partner, kid, family, team
);
create table if not exists rules (
  pattern text primary key,        -- 'calendar:<name>' or a word in a title, lowercase
  who text not null,               -- a name, 'me' or 'family'
  bring text not null default '',  -- who brings them there
  pick text not null default ''    -- who picks them up
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
create table if not exists routes (
  key text primary key,            -- from, to, how and the hour: a travel time asked in the last 20 minutes
  answer text not null,
  at real not null
);
create table if not exists meta (
  key text primary key,
  value text not null
);
