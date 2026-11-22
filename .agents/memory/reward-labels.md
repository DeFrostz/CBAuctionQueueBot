---
name: Reward labels
description: Discord-facing reward names differ from stable internal database keys.
---

The user-facing reward names are `Card`, `Light-Dark`, and `Time-Space`; existing internal keys remain `CARD`, `FEATHER_S`, and `FEATHER_A`.

**Why:** Renaming database keys would break existing stock and queue records.

**How to apply:** Change visible labels through command choices and display mappings, but keep the internal keys stable.
Astrocore rewards use internal keys `ASTRO_DS` (Destroyer Stardust Pack), `ASTRO_DC` (Destroyer Starcore), `ASTRO_GS` (Guardian Stardust Pack) and `ASTRO_GC` (Guardian Starcore). They share one in-game tab, laid out in the order Guardian Starcore, Destroyer Starcore, Guardian Stardust, Destroyer Stardust (see `REWARD_LISTS` in `constants.py`), and are optional: an unset one counts as stock 0 / limit 0.
