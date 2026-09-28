---
name: podcasts
description: Podcasts through the podcasts plugin: search shows in the Apple Podcasts directory (no key), follow them, new episodes of the followed shows this week, a show's latest episodes, and an episode's summary and audio link.
whenToUse: When the owner looks for a podcast, wants to follow or drop one, asks what is new in their podcasts, or wants to hear a particular episode.
---

# podcasts

```sh
podcasts                       # new this week, numbered
podcasts search history        # shows, numbered
podcasts follow 2              # from the last search, or by name
podcasts episodes de dag 5
podcasts play 1                # summary and the audio link
podcasts unfollow de dag
```

- `play` gives the link; say what the episode is about and offer the link, the plugin plays nothing itself.
- The directory allows about twenty searches a minute; when it says to slow down, wait a minute.
