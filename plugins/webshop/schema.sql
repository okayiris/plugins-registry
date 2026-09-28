create table if not exists products (
  id integer primary key autoincrement,
  name text not null,
  price integer not null,              -- cents
  stock integer,                       -- null: no limit
  text text not null default '',
  photo text not null default '',
  visible integer not null default 1,
  position integer not null default 0,
  created text not null
);
create table if not exists orders (
  id integer primary key autoincrement,
  token text not null,                 -- with the id, what lets a customer see their own order
  status text not null,                -- open (waiting for payment), paid, shipped, cancelled
  name text not null,
  email text not null,
  phone text not null default '',
  address text not null default '',
  delivery text not null,              -- pickup or ship
  note text not null default '',
  total integer not null,              -- cents, shipping included
  shipping integer not null default 0,
  payment_id text not null default '',
  pay_url text not null default '',
  created text not null,
  updated text not null
);
create table if not exists lines (
  order_id integer not null references orders (id) on delete cascade,
  product_id integer not null,
  name text not null,
  price integer not null,
  qty integer not null
);
create index if not exists orders_status on orders (status, created);
