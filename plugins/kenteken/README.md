# Kenteken

Look up any Dutch licence plate: make, model, colour, fuel, first registration, and when its APK
runs out, straight from the **RDW**'s open data. Keep your own cars, and Iris tells you when an APK is
coming. No key and no account; owners are never in this data.

## What it does

- `kenteken <plate>` - what vehicle it is, its APK, insurance, and any open recall
- `kenteken` - the cars you keep, the first APK to run out first
- `kenteken add <plate> [name]`, `kenteken remove <plate or name>`

A plate works with or without dashes: `16-RSL-9`, `16rsl9`.

## Say to Iris

- "What car is 16-RSL-9?"
- "When does the APK of my car run out?"
- "Keep AB-123-C as the van."

## Permissions

`internet`: to ask the RDW. Only the plate is sent.
