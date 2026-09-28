---
name: weather
description: The weather at the owner's home or any other place, through the weather plugin (Open-Meteo, free, no key). Now and the next hours, the week ahead, and rain in the next three hours.
whenToUse: When the owner asks about the weather, the temperature, rain, wind, whether to bring an umbrella or a coat, sunrise or sunset, or the air quality. Not for climate history or weather long ago.
---

# weather

```sh
weather                          # home: now, today's range, sun, the next six hours, air quality
weather Lisbon                   # the same for another place
weather week                     # home, seven days
weather week Lisbon
weather rain                     # rain in the next three hours, in quarters of an hour
weather settings set place Utrecht
weather settings set units imperial
```

- What it prints is the answer: say it back short, in the owner's language. "Should I bring an umbrella"
  is `weather rain`, answered with yes or no and the time.
- No home yet: ask where they live and set it with `weather settings set place <city>`.
- A place name that exists in several countries: add the country ("Paris, Texas").
