---
name: wikipedia
description: Look things up on Wikipedia through the wikipedia plugin, in the language the owner chose. A summary, a longer opening, a search, a random article and what happened on this day.
whenToUse: When the owner asks who or what something is, wants the facts about a person, place, event or thing, asks what happened on this day, or explicitly says Wikipedia. Not for news of today or the owner's own notes.
---

# wikipedia

```sh
wikipedia Eiffel Tower           # a short summary and the link
wikipedia more Eiffel Tower      # the whole opening of the article
wikipedia search tallest tower   # which articles match
wikipedia today                  # on this day in history
wikipedia random
wikipedia settings set language nl
```

- Say the summary back in your own words and offer the link.
- An ambiguous subject ("Mercury") falls back to the best search hit; when it is clearly not what the
  owner meant, run `wikipedia search` and ask which one.
