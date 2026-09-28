---
name: mailbox
description: Read this house's own mailbox (the address, received mail with its text, open drafts, sent mail), and with the calendar plugin the meetings and the invitations in the mail.
whenToUse: When the owner asks about mail to this house's own address, wants a mail read out, asks what is in the drafts or what was sent, or asks about an invitation they got by mail. Not for Gmail or Outlook accounts (google-workspace, microsoft-365).
---

# mailbox

```sh
mailbox                 # address, latest received, open drafts, latest sent, and what is coming up
mailbox inbox 10
mailbox read 2          # by inbox number, or by id (a prefix is enough)
mailbox agenda          # meetings and invitations, with the calendar plugin
mailbox accept m2b      # put the invitation in that mail in the calendar
```

- What it prints is the answer: say it back in your own words, in the owner's language.
- It only reads mail. To send or answer a mail, make a draft with `mail draft`; the owner presses Send.
- A line marked `[invitation]` carries a calendar invitation. Offer to put it in the calendar
  (`mailbox accept <id>`); to say yes or no to the organizer, draft a reply to that mail.
- Planning a new meeting is the calendar plugin's (`calendar meet`), and its invitation also goes out
  as a `mail draft` from this house.
