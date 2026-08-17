from database import save_queue_positions_bulk

ITEM_PER_PAGE = 4

REWARD_TYPES = (
    "CARD",
    "FEATHER_S",
    "FEATHER_A",
)


def position(index):
    return (index // ITEM_PER_PAGE + 1, index % ITEM_PER_PAGE + 1)


def get_queue_count_from_rewards(rewards):
    """
    Calculate queue count using only rewards whose limit is > 0.

    A reward with limit = 0 is disabled for queue generation:
    - it does not reduce the queue count
    - none of its stock is assigned to normal queues
    - all of its stock remains Extra
    """
    if not rewards:
        return 0

    reward_map = {row["reward_type"]: row for row in rewards}

    if any(reward not in reward_map for reward in REWARD_TYPES):
        return 0

    counts = []

    for reward in REWARD_TYPES:
        stock = int(reward_map[reward]["stock"])
        limit = int(reward_map[reward]["limit_per_queue"])

        if limit <= 0:
            continue

        counts.append(stock // limit)

    # All rewards disabled -> no queue can be generated.
    if not counts:
        return 0

    return min(counts)


def generate_queue(guild_id, rewards, start_no=1):
    """
    Generate normal queues for one category.

    Rewards with limit = 0 are skipped and remain entirely as Extra.
    """
    if not rewards:
        return 0

    category = rewards[0]["category"]
    reward_map = {r["reward_type"]: r for r in rewards}

    card = reward_map.get("CARD")
    feather_s = reward_map.get("FEATHER_S")
    feather_a = reward_map.get("FEATHER_A")

    if not card or not feather_s or not feather_a:
        return 0

    queue_count = get_queue_count_from_rewards(rewards)

    positions = []

    card_index = 0
    s_index = 0

    # A is displayed after all S stock in the Feather filter.
    a_index = int(feather_s["stock"])

    card_limit = int(card["limit_per_queue"])
    s_limit = int(feather_s["limit_per_queue"])
    a_limit = int(feather_a["limit_per_queue"])

    for i in range(queue_count):
        queue_no = start_no + i

        # CARD - range(0) means the entire Card stock stays Extra.
        for _ in range(card_limit):
            page, slot = position(card_index)
            positions.append((guild_id, category, queue_no, "CARD", page, slot))
            card_index += 1

        # FEATHER S
        for _ in range(s_limit):
            page, slot = position(s_index)
            positions.append((guild_id, category, queue_no, "FEATHER_S", page, slot))
            s_index += 1

        # FEATHER A
        for _ in range(a_limit):
            page, slot = position(a_index)
            positions.append((guild_id, category, queue_no, "FEATHER_A", page, slot))
            a_index += 1

    save_queue_positions_bulk(positions)

    return queue_count


def build_extra_pool(category_rewards, normal_queue_counts):
    """
    Build real remaining positions from multiple categories.

    A reward whose limit is 0 has used count = 0, so its entire stock
    automatically becomes part of the Extra pool.
    """
    pool = {"CARD": [], "FEATHER_S": [], "FEATHER_A": []}

    for category, rewards in category_rewards.items():
        reward_map = {row["reward_type"]: row for row in rewards}
        queue_count = normal_queue_counts.get(category, 0)

        card = reward_map["CARD"]
        feather_s = reward_map["FEATHER_S"]
        feather_a = reward_map["FEATHER_A"]

        card_stock = int(card["stock"])
        s_stock = int(feather_s["stock"])
        a_stock = int(feather_a["stock"])

        card_limit = int(card["limit_per_queue"])
        s_limit = int(feather_s["limit_per_queue"])
        a_limit = int(feather_a["limit_per_queue"])

        # -------------------------
        # Card Extra
        # -------------------------
        card_used = queue_count * card_limit

        for index in range(card_used, card_stock):
            page, slot = position(index)
            pool["CARD"].append({"category": category, "page": page, "slot": slot})

        # -------------------------
        # Feather S Extra
        # -------------------------
        s_used = queue_count * s_limit

        for index in range(s_used, s_stock):
            page, slot = position(index)
            pool["FEATHER_S"].append({"category": category, "page": page, "slot": slot})

        # -------------------------
        # Feather A Extra
        # -------------------------
        a_used = queue_count * a_limit

        # A starts after all S stock of that category.
        a_start = s_stock + a_used
        a_end = s_stock + a_stock

        for index in range(a_start, a_end):
            page, slot = position(index)
            pool["FEATHER_A"].append({"category": category, "page": page, "slot": slot})

    return pool


def generate_extra_queues(guild_id, extra_pool, limits, start_no):
    """
    Combine Extra from linked categories into complete queues.

    Only rewards with limit > 0 participate in Extra queue calculation.
    A reward with limit = 0 remains completely in Extra and does not
    constrain or get consumed by an Extra queue.
    """
    active_rewards = [
        reward
        for reward in REWARD_TYPES
        if int(limits.get(reward, 0)) > 0
    ]

    if not active_rewards:
        remaining = {
            reward: len(extra_pool[reward])
            for reward in REWARD_TYPES
        }
        return 0, remaining

    extra_queue_count = min(
        len(extra_pool[reward]) // int(limits[reward])
        for reward in active_rewards
    )

    positions = []
    pointers = {"CARD": 0, "FEATHER_S": 0, "FEATHER_A": 0}

    for i in range(extra_queue_count):
        queue_no = start_no + i

        for reward_type in active_rewards:
            amount = int(limits[reward_type])

            for _ in range(amount):
                index = pointers[reward_type]
                item = extra_pool[reward_type][index]

                positions.append(
                    (
                        guild_id,
                        item["category"],
                        queue_no,
                        reward_type,
                        item["page"],
                        item["slot"],
                    )
                )

                pointers[reward_type] += 1

    save_queue_positions_bulk(positions)

    remaining = {
        reward: len(extra_pool[reward]) - pointers[reward]
        for reward in REWARD_TYPES
    }

    return extra_queue_count, remaining
