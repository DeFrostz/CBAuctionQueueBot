"""Shared constants. Imported by the database, generator and cogs.

Internal reward keys must stay stable because existing stock and queue
records use them. Only the display names change.
"""

# Fixed categories
CATEGORIES = [
    "Guild League",
    "League Prize",
    "Emperium Overrun",
    "Designed Auction",
]

# Guild League and League Prize share one queue sequence and one Extra pool.
LINKED = (
    "Guild League",
    "League Prize",
)

# Each tuple is one tab (list) in the in-game auction house.
# Items of a tab are laid out one after another, in the order written here:
# the first reward starts at page 1 slot 1 and the next reward continues
# right after all stock of the previous one.
REWARD_LISTS = (
    ("CARD",),
    ("FEATHER_S", "FEATHER_A"),
    # Astrocore, in the order shown in game:
    # Guardian Starcore, Destroyer Starcore, Guardian Stardust, Destroyer Stardust.
    ("ASTRO_GC", "ASTRO_DC", "ASTRO_GS", "ASTRO_DS"),
)

# Display / processing order of rewards.
REWARD_TYPES = tuple(reward for tab in REWARD_LISTS for reward in tab)

# Must be configured before a category can be generated.
# Every other reward is optional: when it is not set it counts as 0 and
# stays out of the queues.
REQUIRED_REWARDS = ("CARD", "FEATHER_S", "FEATHER_A")

# Discord-facing names (with emoji).
REWARD_NAMES = {
    "CARD": "🃏 Card",
    "FEATHER_S": "🌗 Light-Dark",
    "FEATHER_A": "⏳ Time-Space",
    "ASTRO_DS": "🔴 Destroyer Stardust Pack",
    "ASTRO_DC": "🟥 Destroyer Starcore",
    "ASTRO_GS": "🔵 Guardian Stardust Pack",
    "ASTRO_GC": "🟦 Guardian Starcore",
}

ITEM_PER_PAGE = 4


def position(index):
    """Map a zero-based item index to (page, slot), both starting at 1."""
    return (index // ITEM_PER_PAGE + 1, index % ITEM_PER_PAGE + 1)


def list_offset(reward, stocks):
    """
    Index where `reward` starts inside its tab, given {reward: stock}.

    It is the total stock of the rewards listed before it in the same tab
    (e.g. Time-Space starts after all Light-Dark stock).
    """
    for tab in REWARD_LISTS:
        if reward in tab:
            return sum(int(stocks.get(r, 0)) for r in tab[: tab.index(reward)])
    return 0
