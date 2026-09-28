# Mailbox

Read the mailbox of this house. The window and the command show the same mail: the address, the latest
mail that came in, the open drafts and the mail this house sent. With the
calendar plugin, your meetings and the invitations in your mail show here too.

**It only reads mail.** The command never sends a mail and never makes or discards a draft. Sending
stays with `mail draft`, on the owner's screen, where they press Send themselves.

## Command

```
mailbox                 the address, the latest received mail, the open drafts, the latest sent mail
                        and, with the calendar plugin, what is coming up
mailbox inbox [n]       the last n received mails, with sender, subject and date (default 10)
mailbox sent [n]        the last n sent mails, with recipient, subject and date (default 10)
mailbox read <id|n>     the full text of one mail, by id (a prefix is enough) or by inbox number
mailbox agenda          the coming meetings and the invitations in the mail (calendar plugin)
mailbox accept <id>     put the invitation in that mail in the calendar (calendar plugin)
```

The answer is short and readable, made for the conversation, not a log. Times are the house's own
time, the same in the command and the window. Only received mail carries a text in this house; for sent
mail the bridge keeps when it went and to whom, and the command says so.

A mail that carries a calendar invitation (an .ics, as Google, Outlook and Apple send them) is marked
`[invitation]`, and reading it shows the text without the raw invitation code.

## Window

The overview shows the latest received mail, what is coming up in the calendar and the open drafts.
Recent received and Latest sent list more. Click or tap a mail to read it; a mail with an invitation
has a **Put in calendar** button. When there is nothing yet it says so plainly.

Every button does the work itself, in the window: Reload reads the bridge again and shows the time it
was read next to the buttons, the three views rearrange the window, and Put in calendar says what it did
next to it. Nothing here is handed to the conversation: a button that only sends a sentence to Iris is
not a button that works (AGENTS.md, "every button gives a visible answer").

That read needs the house to allow `/mail` for its own windows, the way it allows `/socials`
(`src/herkomst.ts`: origin `null` plus the bridge's window secret). Without it the window says what
went wrong where the answer belongs, at the button.

## With the calendar

Mailbox and calendar are two plugins that work as one: the calendar plans meetings and writes the
invitations, which go out as a draft from this mailbox; invitations that come into this mailbox go into
the calendar. Without the calendar plugin the mailbox works as before and says where the meetings would
show.

## Permissions

- `internet`: the command and the window read the mail through the bridge of this house.
