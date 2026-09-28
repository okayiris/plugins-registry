---
name: kenteken
description: Dutch licence plates through the kenteken plugin (RDW open data, no key): make, model, colour, fuel, first registration, APK expiry, WAM insurance and open recalls, and the owner's own cars with their APK.
whenToUse: When the owner gives a Dutch licence plate or asks what car it is, when an APK runs out, whether a car is insured or has a recall, or wants a car kept to watch its APK. Not for who owns a car: that is not public.
---

# kenteken

```sh
kenteken 16-RSL-9          # one plate
kenteken                   # the owner's cars and their APK
kenteken add 16-RSL-9 Toyota
kenteken remove Toyota
```

- An APK within 60 days says so; offer to put booking it in the calendar or on a list.
- The RDW does not know who owns a car. Say so if asked.
