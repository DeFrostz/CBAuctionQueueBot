from database import save_queue_positions_bulk

ITEM_PER_PAGE = 4

REWARD_TYPES = (
    "CARD",
    "FEATHER_S",
    "FEATHER_A",
)


def position(index):
    return (
        index // ITEM_PER_PAGE + 1,
        index % ITEM_PER_PAGE + 1
    )


def get_queue_count_from_rewards(rewards):
    if not rewards:
        return 0

    reward_map = {
        row["reward_type"]: row
        for row in rewards
    }

    if any(r not in reward_map for r in REWARD_TYPES):
        return 0

    return min(
        reward_map[reward]["stock"]
        // reward_map[reward]["limit_per_queue"]
        for reward in REWARD_TYPES
    )


def generate_queue(
    guild_id,
    rewards,
    start_no=1
):
    """
    Generate normal queues for one category.
    """

    if not rewards:
        return 0

    category = rewards[0]["category"]

    reward_map = {
        r["reward_type"]: r
        for r in rewards
    }

    card = reward_map.get("CARD")
    feather_s = reward_map.get("FEATHER_S")
    feather_a = reward_map.get("FEATHER_A")

    if not card or not feather_s or not feather_a:
        return 0

    queue_count = get_queue_count_from_rewards(
        rewards
    )

    positions = []

    card_index = 0
    s_index = 0

    # A อยู่ต่อจาก S ใน Feather filter
    a_index = feather_s["stock"]

    for i in range(queue_count):

        queue_no = start_no + i

        # CARD
        for _ in range(card["limit_per_queue"]):

            page, slot = position(card_index)

            positions.append((
                guild_id,
                category,
                queue_no,
                "CARD",
                page,
                slot
            ))

            card_index += 1

        # FEATHER S
        for _ in range(
            feather_s["limit_per_queue"]
        ):

            page, slot = position(s_index)

            positions.append((
                guild_id,
                category,
                queue_no,
                "FEATHER_S",
                page,
                slot
            ))

            s_index += 1

        # FEATHER A
        for _ in range(
            feather_a["limit_per_queue"]
        ):

            page, slot = position(a_index)

            positions.append((
                guild_id,
                category,
                queue_no,
                "FEATHER_A",
                page,
                slot
            ))

            a_index += 1

    save_queue_positions_bulk(positions)

    return queue_count


def build_extra_pool(
    category_rewards,
    normal_queue_counts
):
    """
    Build real remaining positions from multiple categories.

    Returns:
    {
        "CARD": [
            {
                "category": "...",
                "page": 1,
                "slot": 1
            }
        ],
        ...
    }
    """

    pool = {
        "CARD": [],
        "FEATHER_S": [],
        "FEATHER_A": []
    }

    for category, rewards in category_rewards.items():

        reward_map = {
            row["reward_type"]: row
            for row in rewards
        }

        queue_count = normal_queue_counts.get(
            category,
            0
        )

        card = reward_map["CARD"]
        feather_s = reward_map["FEATHER_S"]
        feather_a = reward_map["FEATHER_A"]

        # -------------------------
        # Card Extra
        # -------------------------

        card_used = (
            queue_count
            * card["limit_per_queue"]
        )

        for index in range(
            card_used,
            card["stock"]
        ):

            page, slot = position(index)

            pool["CARD"].append({
                "category": category,
                "page": page,
                "slot": slot
            })

        # -------------------------
        # Feather S Extra
        # -------------------------

        s_used = (
            queue_count
            * feather_s["limit_per_queue"]
        )

        for index in range(
            s_used,
            feather_s["stock"]
        ):

            page, slot = position(index)

            pool["FEATHER_S"].append({
                "category": category,
                "page": page,
                "slot": slot
            })

        # -------------------------
        # Feather A Extra
        # -------------------------

        a_used = (
            queue_count
            * feather_a["limit_per_queue"]
        )

        # A เริ่มหลัง S stock ของ category นั้น
        a_start = (
            feather_s["stock"]
            + a_used
        )

        a_end = (
            feather_s["stock"]
            + feather_a["stock"]
        )

        for index in range(
            a_start,
            a_end
        ):

            page, slot = position(index)

            pool["FEATHER_A"].append({
                "category": category,
                "page": page,
                "slot": slot
            })

    return pool


def generate_extra_queues(
    guild_id,
    extra_pool,
    limits,
    start_no
):
    """
    Combine extra from linked categories and create
    complete queues.

    Each reward keeps its ORIGINAL category/page/slot.
    """

    extra_queue_count = min(
        len(extra_pool["CARD"])
        // limits["CARD"],

        len(extra_pool["FEATHER_S"])
        // limits["FEATHER_S"],

        len(extra_pool["FEATHER_A"])
        // limits["FEATHER_A"]
    )

    positions = []

    pointers = {
        "CARD": 0,
        "FEATHER_S": 0,
        "FEATHER_A": 0
    }

    for i in range(extra_queue_count):

        queue_no = start_no + i

        for reward_type in REWARD_TYPES:

            amount = limits[reward_type]

            for _ in range(amount):

                index = pointers[reward_type]

                item = extra_pool[
                    reward_type
                ][index]

                positions.append((
                    guild_id,

                    # original source category
                    item["category"],

                    # shared queue number
                    queue_no,

                    reward_type,
                    item["page"],
                    item["slot"]
                ))

                pointers[reward_type] += 1

    save_queue_positions_bulk(positions)

    remaining = {
        reward: (
            len(extra_pool[reward])
            - pointers[reward]
        )
        for reward in REWARD_TYPES
    }

    return extra_queue_count, remaining