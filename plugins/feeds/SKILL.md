---
name: feeds
description: The news sites and blogs the owner follows, read from their RSS or Atom feeds through the feeds plugin. The newest items, a search across them, and the summary and link of one item.
whenToUse: When the owner asks what is in the news, what is new on a site or blog they follow, whether there is anything about a subject, or wants a feed followed or dropped. Not for searching the whole web.
---

# feeds

```sh
feeds                        # the newest items of all feeds together
feeds latest NOS 5           # the five newest of one feed
feeds search election        # items about a subject
feeds read 3                 # summary and link of item 3 of the last list
feeds list
feeds add "NOS" https://feeds.nos.nl/nosnieuwsalgemeen
feeds remove "NOS"
feeds refresh                # read again now instead of the copy from up to 15 minutes ago
```

- Read the headlines back briefly and offer to open one; `feeds read <n>` refers to the list printed last.
- A site's own address usually works for `feeds add`: the plugin finds the feed the page points to.
- Only feeds the owner follows can be read. For news on something else, suggest a feed to follow.
