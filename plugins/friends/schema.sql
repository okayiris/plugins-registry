create table if not exists posts (
  id integer primary key autoincrement,
  text text not null default '',
  photo integer,                        -- photos.id, or null
  audience text not null,               -- friends (only friends see it) or public (everyone, and followers)
  at integer not null                   -- seconds since 1970
);
create table if not exists photos (
  id integer primary key autoincrement,
  type text not null,                   -- image/jpeg, image/png, image/gif or image/webp
  data blob not null,
  at integer not null
);
-- Other houses, by the first part of their address (anna for anna.okayiris.com).
create table if not exists friends (
  house text primary key,
  name text not null default '',
  state text not null,                  -- sent (I asked), asked (they asked me), friends, blocked
  my_key text,                          -- what they show my house to see my friends-only posts
  their_key text,                       -- what I show their house
  at integer not null
);
create table if not exists follows (    -- houses I follow: their public posts in my feed
  house text primary key,
  name text not null default '',
  at integer not null
);
create table if not exists followers (  -- houses that follow me; each one checked with that house itself
  house text primary key,
  name text not null default '',
  at integer not null
);
create table if not exists likes (
  post_id integer not null,
  house text not null,
  name text not null default '',
  at integer not null,
  primary key (post_id, house)
);
create table if not exists comments (
  id integer primary key autoincrement,
  post_id integer not null,
  house text not null,
  name text not null default '',
  text text not null,
  at integer not null
);
-- What friends and followed houses posted, as last fetched.
create table if not exists feed (
  house text not null,
  post_id integer not null,
  name text not null default '',
  text text not null default '',
  audience text not null,
  photo integer not null default 0,
  at integer not null,
  likes integer not null default 0,
  comments integer not null default 0,
  liked integer not null default 0,
  thread text not null default '[]',    -- the latest comments, as JSON; only friends get them
  primary key (house, post_id)
);
create table if not exists feed_photos (
  house text not null,
  post_id text not null,                -- a post id, or avatar
  type text not null,
  data blob not null,
  at integer not null,
  primary key (house, post_id)
);
create table if not exists news (       -- requests, likes, comments and followers, for the owner
  id integer primary key autoincrement,
  kind text not null,                   -- request, friends, like, comment, follower
  house text not null,
  name text not null default '',
  post_id integer,
  text text not null default '',
  at integer not null,
  seen integer not null default 0
);
create index if not exists comments_post on comments (post_id, id);
create index if not exists feed_at on feed (at);
