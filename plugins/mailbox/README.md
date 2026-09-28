# Mailbox

Read the mailbox of this house. The window and the command show the same mail: the address, the
open drafts, the mail that came in, and the mail this house sent.

**It only reads.** The command never sends a mail and never makes or discards a draft. Sending stays
with `mail draft`, on the owner's screen, where they press Send themselves.

## Command

```
mailbox                 the address, the open drafts and the latest sent mail
mailbox inbox [n]       the last n received mails, with sender, subject and date (default 10)
mailbox sent [n]        the last n sent mails, with recipient, subject and date (default 10)
mailbox read <id|n>     the full text of one mail, by id (a prefix is enough) or by inbox number
```

The answer is short and readable, made for the conversation, not a log. Only received mail carries a
text in this house; for sent mail the bridge keeps when it went and to whom, and the command says so.

## Window

The window lists the inbox and the sent mail with sender, subject and time. Click or tap a mail to
read it. When there is nothing yet it says so plainly.

Every button does the work itself, in the window: Reload reads the bridge again and shows the time it
was read next to the buttons, and the three views (Overview, Recent received, Latest sent) rearrange
the window. Nothing here is handed to the conversation: a button that only sends a sentence to Iris is
not a button that works (AGENTS.md, "every button gives a visible answer").

That read needs the house to allow `/mail` for its own windows, the way it allows `/socials`
(`src/herkomst.ts`: origin `null` plus the bridge's window secret). Without it the window says what
went wrong where the answer belongs, at the button.

## Permissions

- `internet`: the command and the window read the mail through the bridge of this house.
