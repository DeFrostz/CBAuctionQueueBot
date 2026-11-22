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


# Rewards that are spread over the queues by party instead of being counted
# in every queue: everyone gets the same base, the remainder is handed out as
# +1 along the party rotation. Each group has its own rotation pointer.
SPREAD_GROUPS = {
    "card": ("CARD",),
    "astro": ("ASTRO_GC", "ASTRO_DC", "ASTRO_GS", "ASTRO_DS"),
}
SPREAD_REWARDS = tuple(
    reward for rewards in SPREAD_GROUPS.values() for reward in rewards
)


# Guild League auction table per rank (best first).
# pool  = Auction Reward: (Card, Light-Dark, Time-Space, Astrocore of each kind)
# limit = Auction Limit : same order, amount one queue may take
RANK_TABLE = (
    ("Peak King",       (23, 90, 105, 10), (3, 10, 10, 4)),
    ("Supreme Warband", (21, 87, 105, 10), (3, 9, 10, 4)),
    ("Honor Soul",      (20, 84, 105, 9),  (3, 9, 10, 4)),
    ("The Chosen One",  (19, 81, 105, 9),  (2, 8, 10, 4)),
    ("Glorious Legend", (18, 78, 105, 9),  (2, 8, 10, 4)),
    ("Immortal Myth",   (17, 75, 105, 8),  (2, 7, 10, 3)),
    ("Eternal Monarch", (16, 72, 105, 8),  (2, 7, 10, 3)),
    ("Omni Ruler",      (15, 69, 105, 8),  (2, 7, 10, 3)),
    ("Bright Sun",      (8, 60, 105, 7),   (1, 6, 10, 3)),
    ("Glorious Moon",   (7, 55, 100, 6),   (1, 5, 10, 2)),
    ("Shining Star",    (6, 50, 90, 6),    (1, 5, 9, 2)),
    ("Platinum",        (5, 45, 80, 5),    (1, 4, 8, 2)),
    ("Gold",            (4, 40, 70, 4),    (1, 4, 7, 2)),
    ("Silver",          (2, 35, 60, 4),    (1, 3, 6, 2)),
    ("Bronze",          (2, 30, 50, 3),    (1, 3, 5, 1)),
)


def rank_values(rank_name):
    """{reward: (stock, limit)} for a rank, or None if the rank is unknown."""
    for name, pool, limit in RANK_TABLE:
        if name == rank_name:
            card, light_dark, time_space, astro = pool
            l_card, l_light_dark, l_time_space, l_astro = limit
            values = {
                "CARD": (card, l_card),
                "FEATHER_S": (light_dark, l_light_dark),
                "FEATHER_A": (time_space, l_time_space),
            }
            for reward in SPREAD_GROUPS["astro"]:
                values[reward] = (astro, l_astro)
            return values
    return None


# Emperium Overrun auction table per league and rank (rank 1 = best).
# Same layout as RANK_TABLE: pool and limit as (Card, Light-Dark, Time-Space,
# Astrocore of each kind).
EMPERIUM_CATEGORY = "Emperium Overrun"

EMPERIUM_TABLE = {
    "Advance": (
        ((20, 150, 170, 20), (2, 15, 17, 4)),
        ((20, 140, 160, 18), (2, 14, 16, 4)),
        ((20, 140, 160, 18), (2, 14, 16, 4)),
        ((15, 120, 150, 16), (2, 12, 15, 3)),
        ((15, 120, 150, 16), (2, 12, 15, 3)),
        ((15, 120, 150, 16), (2, 12, 15, 3)),
        ((12, 100, 150, 14), (2, 10, 15, 3)),
        ((12, 100, 150, 14), (2, 10, 15, 3)),
    ),
    "Normal": (
        ((10, 80, 140, 10), (1, 8, 14, 2)),
        ((9, 75, 130, 10), (1, 8, 13, 2)),
        ((8, 70, 120, 10), (1, 7, 12, 2)),
        ((5, 65, 110, 8), (1, 7, 11, 2)),
        ((5, 60, 100, 8), (1, 6, 10, 2)),
        ((5, 50, 80, 6), (1, 5, 8, 1)),
        ((2, 30, 30, 4), (1, 3, 3, 1)),
        ((1, 20, 20, 2), (1, 2, 2, 1)),
    ),
}


def emperium_rank_values(league, rank):
    """{reward: (stock, limit)} for an Emperium league and rank, or None."""
    ranks = EMPERIUM_TABLE.get(league)
    if ranks is None or not 1 <= rank <= len(ranks):
        return None
    (card, light_dark, time_space, astro), (
        l_card,
        l_light_dark,
        l_time_space,
        l_astro,
    ) = ranks[rank - 1]
    values = {
        "CARD": (card, l_card),
        "FEATHER_S": (light_dark, l_light_dark),
        "FEATHER_A": (time_space, l_time_space),
    }
    for reward in SPREAD_GROUPS["astro"]:
        values[reward] = (astro, l_astro)
    return values
