create table if not exists cart (
  id integer primary key autoincrement,
  shop text not null,
  shop_url text not null,
  kind text not null,
  product_id text not null default '',
  variant_id text not null default '',
  variant text not null default '',
  title text not null,
  price integer,
  currency text not null default '',
  image text not null default '',
  url text not null,
  qty integer not null default 1,
  added text not null
);
create table if not exists saved (
  id integer primary key autoincrement,
  shop text not null,
  shop_url text not null,
  kind text not null,
  product_id text not null default '',
  handle text not null default '',
  title text not null,
  price integer,
  first_price integer,
  currency text not null default '',
  image text not null default '',
  url text not null unique,
  added text not null
);
create table if not exists orders (
  id integer primary key autoincrement,
  shop text not null,
  shop_url text not null,
  items text not null,
  total integer,
  currency text not null default '',
  checkout text not null,
  created text not null
);
