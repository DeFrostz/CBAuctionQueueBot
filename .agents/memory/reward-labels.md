---
name: Reward labels
description: Discord-facing reward names differ from stable internal database keys.
---

The user-facing reward names are `Card`, `Light-Dark`, and `Time-Space`; existing internal keys remain `CARD`, `FEATHER_S`, and `FEATHER_A`.

**Why:** Renaming database keys would break existing stock and queue records.

**How to apply:** Change visible labels through command choices and display mappings, but keep the internal keys stable.