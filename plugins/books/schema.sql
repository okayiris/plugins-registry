create table if not exists books (
  id integer primary key autoincrement,
  olkey text not null default '',
  title text not null,
  author text not null default '',
  year integer,
  pages integer,
  state text not null check (state in ('want', 'reading', 'read')),
  stars integer,
  started text,
  finished text,
  added text not null,
  updated text not null
);
create index if not exists books_state on books (state, updated);
create table if not exists notes (
  id integer primary key autoincrement,
  book_id integer not null references books (id) on delete cascade,
  text text not null,
  created text not null
);
