---
name: ns
description: Dutch trains live from the NS through the trains command of the ns plugin, with the owner's own free key in the vault. Departures with delays, track changes and cancellations, the next trips from A to B (also at a time or to arrive by a time), and disruptions and works.
whenToUse: When the owner asks about a train in the Netherlands: when the next one leaves, how to get somewhere by train, whether their train is late or cancelled, which track, or whether there are disruptions. Not for buses, trams or trains abroad.
---

# ns (command: trains)

```sh
trains                                       # departures from the home station
trains Amsterdam                             # from another station
trains to Amsterdam                          # the next trips from home
trains to "Den Haag" from Utrecht at 17:30
trains to Schiphol arrive 09:00              # arrive before 9
trains work / trains home                    # the commute, both ways
trains disruptions                           # or: trains disruptions Zwolle
trains stations zuid                         # find a station
trains settings set home Utrecht Centraal
trains key ask                               # the owner pastes a key in the vault
```

- "+3" after a time is minutes late. Say track changes and cancellations first; they matter most.
- Times are Dutch time.
- No key yet: it is free at apiportal.ns.nl (subscribe to Ns-App, copy the primary key); then `trains key ask`.
