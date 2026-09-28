create table if not exists types (
  id integer primary key autoincrement,
  name text not null,
  minutes integer not null,
  kind text not null check (kind in ('place', 'video', 'webinar')),
  place text not null default '',          -- the address, for kind place
  seats integer not null default 1,        -- for a webinar: how many may book one session
  text text not null default '',
  visible integer not null default 1,
  position integer not null default 0,
  created text not null
);
create table if not exists sessions (       -- the fixed moments of a webinar
  id integer primary key autoincrement,
  type_id integer not null references types (id) on delete cascade,
  starts text not null,                    -- ISO, with the house's offset
  seats integer not null,
  link text not null default '',
  cancelled integer not null default 0
);
create table if not exists bookings (
  id integer primary key autoincrement,
  token text not null,                     -- with the id, what lets a guest see or cancel their booking
  type_id integer not null,
  session_id integer,
  starts text not null,
  ends text not null,
  name text not null,
  email text not null,
  note text not null default '',
  link text not null default '',           -- the video link, when there is one
  status text not null default 'booked',   -- booked or cancelled
  created text not null
);
create table if not exists blocks (         -- time the owner is not available, beyond the weekly hours
  id integer primary key autoincrement,
  starts text not null,
  ends text not null,
  note text not null default ''
);
create index if not exists bookings_starts on bookings (status, starts);
