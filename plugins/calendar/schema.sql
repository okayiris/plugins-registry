-- The meetings of this house: planned here, or taken over from an invitation in the mailbox.
-- Times are local wall-clock time of the house, as YYYY-MM-DDTHH:MM.
CREATE TABLE IF NOT EXISTS meetings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  uid TEXT NOT NULL UNIQUE,            -- the UID in every invitation, so an update or cancel finds it back
  title TEXT NOT NULL,
  starts TEXT NOT NULL,
  ends TEXT NOT NULL,
  place TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  guests TEXT NOT NULL DEFAULT '',     -- mail addresses, comma separated
  organizer TEXT NOT NULL DEFAULT '',  -- who invited: this house's address, or the sender of the invitation
  source TEXT NOT NULL DEFAULT 'own',  -- own: planned here; mail: taken from an invitation
  mail_id TEXT NOT NULL DEFAULT '',    -- the mail it came from (source mail)
  sequence INTEGER NOT NULL DEFAULT 0, -- raised on every change, as invitations require
  status TEXT NOT NULL DEFAULT 'confirmed',  -- confirmed or cancelled
  created TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS meetings_starts ON meetings (starts);
