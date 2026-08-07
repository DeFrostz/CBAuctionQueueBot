from database import (
    clear_queue,
    save_queue_positions_bulk
)


ITEM_PER_PAGE = 4


def position(index):
    return (
        index // ITEM_PER_PAGE + 1,
        index % ITEM_PER_PAGE + 1
    )


def generate_queue(
    guild_id,
    rewards
):
    """
    Generate the queue plan for a single category represented by `rewards`.

    `rewards` is expected to be a list of rows (sqlite3.Row) all belonging to
    the same category. Returns the number of queues generated (queue_count).
    """
    if not rewards:
        return 0

    # Determine category from provided rewards (they should all share the same)
    category = rewards[0]["category"]

    # Clear only this category's existing queue
    clear_queue(guild_id, category)

    reward_map = {r["reward_type"]: r for r in rewards}

    card = reward_map.get("CARD")
    feather_s = reward_map.get("FEATHER_S")
    feather_a = reward_map.get("FEATHER_A")

    # If any reward missing, nothing to generate
    if not card or not feather_s or not feather_a:
        return 0

    # Max queues available is limited by stock // limit_per_queue for each reward
    queue_count = min(
        card["stock"] // card["limit_per_queue"],
        feather_s["stock"] // feather_s["limit_per_queue"],
        feather_a["stock"] // feather_a["limit_per_queue"]
    )

    positions = []  # collect tuples for bulk insert

    card_index = 0
    s_index = 0
    # A starts after S stock positions
    a_index = feather_s["stock"]

    for queue in range(1, queue_count + 1):
        # CARD
        for _ in range(card["limit_per_queue"]):
            page, slot = position(card_index)
            positions.append((guild_id, category, queue, "CARD", page, slot))
            card_index += 1

        # FEATHER_S
        for _ in range(feather_s["limit_per_queue"]):
            page, slot = position(s_index)
            positions.append((guild_id, category, queue, "FEATHER_S", page, slot))
            s_index += 1

        # FEATHER_A
        for _ in range(feather_a["limit_per_queue"]):
            page, slot = position(a_index)
            positions.append((guild_id, category, queue, "FEATHER_A", page, slot))
            a_index += 1

    # Bulk insert all positions in a single transaction for performance
    if positions:
        save_queue_positions_bulk(positions)

    return queue_count
