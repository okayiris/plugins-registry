---
name: units
description: Convert between units through the units plugin, offline and exact: length, weight, volume and US cooking measures, temperature, speed, area, data sizes, time and fuel use.
whenToUse: When the owner asks how much something is in another unit ("how many grams is a cup of", "350 F in C", "5 miles in km", "what is 6 feet in cm"). Not for money (currency) or time zones (worldclock).
---

# units

```sh
units 5 miles km
units 350 F to C
units 2 cups ml
units 180 lb          # to the other side: metric to imperial and back
units 30 mpg          # to l/100km
units list
```

- Feet and inches together ("6 ft 2"): convert them one by one and add them up.
- Cups and spoons are US measures; say so for a British recipe. A cup of flour in grams depends on the
  flour, not on this plugin.
