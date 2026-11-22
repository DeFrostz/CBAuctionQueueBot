"""Shared constants. Imported by the database, generator and cogs.

Internal reward keys (CARD, FEATHER_S, FEATHER_A) must stay stable because
existing stock and queue records use them. Only the display names change.
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

# Display / processing order of rewards.
REWARD_TYPES = (
    "CARD",
    "FEATHER_S",
    "FEATHER_A",
)

# Discord-facing names (with emoji).
REWARD_NAMES = {
    "CARD": "🃏 Card",
    "FEATHER_S": "🌗 Light-Dark",
    "FEATHER_A": "⏳ Time-Space",
}

ITEM_PER_PAGE = 4


def position(index):
    """Map a zero-based item index to (page, slot), both starting at 1."""
    return (index // ITEM_PER_PAGE + 1, index % ITEM_PER_PAGE + 1)
