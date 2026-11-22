---
name: Reward labels
description: Discord-facing reward names differ from stable internal database keys.
---

The user-facing reward names are `Card`, `Light-Dark`, and `Time-Space`; existing internal keys remain `CARD`, `FEATHER_S`, and `FEATHER_A`.

**Why:** Renaming database keys would break existing stock and queue records.

**How to apply:** Change visible labels through command choices and display mappings, but keep the internal keys stable.
Astrocore rewards use internal keys `ASTRO_DS` (Destroyer Stardust Pack), `ASTRO_DC` (Destroyer Starcore), `ASTRO_GS` (Guardian Stardust Pack) and `ASTRO_GC` (Guardian Starcore). They share one in-game tab, laid out in the order Guardian Starcore, Destroyer Starcore, Guardian Stardust, Destroyer Stardust (see `REWARD_LISTS` in `constants.py`), and are optional: an unset one counts as stock 0 / limit 0.

With a party plan set (`/setparty`), Card and Astrocore are "spread" rewards (`SPREAD_GROUPS` in `constants.py`): their limit is a cap per queue (0 = no cap), they stay out of the queue count, and each queue gets pool // queues plus a +1 for the remainder along the party rotation. Card and Astrocore have separate rotation pointers (`card_start`, `astro_start`). `/setrank` fills GL and LP from `RANK_TABLE`.

Emperium Overrun has its own party plan (`emperium_plan`, `/setparty area:Emperium Overrun`) and rank table (`EMPERIUM_TABLE`, `/setemperium`). Feathers decide the queues; Card and Astrocore get pool // queues per queue (capped by the limit) and the remainder ("Extra After Calculate") goes one item per party along the party rotation from separate Card / Astrocore pointers. `/emperiumplan` posts every rank grouped like "Condition Rank 4 5 6".
