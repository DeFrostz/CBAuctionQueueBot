from constants import (
    LINKED,
    REQUIRED_REWARDS,
    REWARD_TYPES,
    list_offset,
    position,
)
from database import clear_queue, get_rewards, save_queue_positions_bulk


def reward_values(rewards, exclude=()):
    """
    Return ({reward: stock}, {reward: limit}) for every reward type.

    A reward with no row (optional rewards that were never set) counts as
    stock 0 / limit 0. Rewards in `exclude` are handled outside the normal
    queues (spread by party), so their limit counts as 0 here.
    """
    reward_map = {row["reward_type"]: row for row in rewards}
    stocks = {}
    limits = {}

    for reward in REWARD_TYPES:
        row = reward_map.get(reward)
        stocks[reward] = int(row["stock"]) if row is not None else 0
        limits[reward] = int(row["limit_per_queue"]) if row is not None else 0
        if reward in exclude:
            limits[reward] = 0

    return stocks, limits


def has_required_rewards(rewards):
    reward_map = {row["reward_type"] for row in rewards}
    return all(reward in reward_map for reward in REQUIRED_REWARDS)


def get_queue_count_from_rewards(rewards, exclude=()):
    """
    Calculate queue count using only rewards whose limit is > 0.

    A reward with limit = 0 is disabled for queue generation:
    - it does not reduce the queue count
    - none of its stock is assigned to normal queues
    - all of its stock remains Extra
    """
    if not rewards or not has_required_rewards(rewards):
        return 0

    stocks, limits = reward_values(rewards, exclude)

    counts = [
        stocks[reward] // limits[reward]
        for reward in REWARD_TYPES
        if limits[reward] > 0
    ]

    # All rewards disabled -> no queue can be generated.
    if not counts:
        return 0

    return min(counts)


def generate_queue(guild_id, rewards, start_no=1, exclude=()):
    """
    Generate normal queues for one category.

    Rewards with limit = 0 are skipped and remain entirely as Extra.
    """
    if not rewards or not has_required_rewards(rewards):
        return 0

    category = rewards[0]["category"]
    stocks, limits = reward_values(rewards, exclude)
    queue_count = get_queue_count_from_rewards(rewards, exclude)

    # Next unused index of each reward inside its tab. Rewards that share a
    # tab (Light-Dark / Time-Space, the Astrocore kinds) start after the
    # stock of the ones listed before them.
    pointers = {reward: list_offset(reward, stocks) for reward in REWARD_TYPES}

    positions = []

    for i in range(queue_count):
        queue_no = start_no + i

        # limit 0 -> range(0): the entire stock stays Extra.
        for reward in REWARD_TYPES:
            for _ in range(limits[reward]):
                page, slot = position(pointers[reward])
                positions.append((guild_id, category, queue_no, reward, page, slot))
                pointers[reward] += 1

    save_queue_positions_bulk(positions)

    return queue_count


def build_extra_pool(category_rewards, normal_queue_counts, exclude=()):
    """
    Build real remaining positions from multiple categories.

    A reward whose limit is 0 has used count = 0, so its entire stock
    automatically becomes part of the Extra pool.
    """
    pool = {reward: [] for reward in REWARD_TYPES}

    for category, rewards in category_rewards.items():
        stocks, limits = reward_values(rewards, exclude)
        queue_count = normal_queue_counts.get(category, 0)

        for reward in REWARD_TYPES:
            offset = list_offset(reward, stocks)
            used = queue_count * limits[reward]

            for index in range(offset + used, offset + stocks[reward]):
                page, slot = position(index)
                pool[reward].append(
                    {"category": category, "page": page, "slot": slot}
                )

    return pool


def count_extra_queues(extra_pool, limits):
    """How many complete Extra queues the pool can make (nothing is saved)."""
    active_rewards = [
        reward
        for reward in REWARD_TYPES
        if int(limits.get(reward, 0)) > 0
    ]

    if not active_rewards:
        return 0

    return min(
        len(extra_pool[reward]) // int(limits[reward])
        for reward in active_rewards
    )


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

    extra_queue_count = count_extra_queues(extra_pool, limits)

    positions = []
    pointers = {reward: 0 for reward in REWARD_TYPES}

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


def get_skip_reason(rewards, exclude=()):
    """Return why a category cannot be generated, or None if it is ready."""
    if not has_required_rewards(rewards):
        return "missing reward config"

    stocks, limits = reward_values(rewards, exclude)

    if any(limit < 0 for limit in limits.values()):
        return "invalid negative limit"

    active_rewards = [reward for reward in REWARD_TYPES if limits[reward] > 0]

    if not active_rewards:
        return "all limits are 0"

    if any(stocks[reward] < 1 for reward in active_rewards):
        return "missing stock for active reward"

    return None


def check_categories(guild_id, categories, exclude=(), exclude_for=LINKED):
    """
    Split categories into ready and skipped.

    Returns ({category: reward rows}, [(category, reason), ...]).
    The dict keeps the order of `categories`.
    """
    ready = {}
    skipped = []

    for category in categories:
        rows = get_rewards(guild_id, category)
        reason = get_skip_reason(rows, exclude if category in exclude_for else ())

        if reason:
            skipped.append((category, reason))
        else:
            ready[category] = rows

    return ready, skipped


def generate_all(guild_id, category_rewards, exclude=(), exclude_for=LINKED):
    """
    Regenerate queues for every ready category (from check_categories).

    Linked categories share one queue sequence. Their leftovers are pooled
    into GL/LP Extra queues, even when only one of them is ready.
    """
    linked_ready = [cat for cat in LINKED if cat in category_rewards]

    # Linked categories share queue numbers, so clear both together to avoid
    # stale rows from a skipped partner colliding with the new numbers.
    to_clear = set(category_rewards)
    if linked_ready:
        to_clear.update(LINKED)

    for category in to_clear:
        clear_queue(guild_id, category)

    results = {}
    normal_queue_counts = {}
    linked_next_queue_no = 1

    for category, rows in category_rewards.items():
        start_no = linked_next_queue_no if category in LINKED else 1
        count = generate_queue(
            guild_id, rows, start_no, exclude if category in exclude_for else ()
        )

        if category in LINKED:
            linked_next_queue_no += count

        normal_queue_counts[category] = count
        results[category] = {
            "count": count,
            "start": start_no,
            "end": start_no + count - 1 if count > 0 else 0,
        }

    summary = {
        "results": results,
        "extra_count": 0,
        "extra_start": None,
        "extra_end": None,
        "remaining_extra": None,
        "extra_limits_from": None,
        "linked_limits_differ": False,
    }

    if not linked_ready:
        return summary

    extra_pool = build_extra_pool(
        {cat: category_rewards[cat] for cat in linked_ready},
        {cat: normal_queue_counts[cat] for cat in linked_ready},
        exclude,
    )

    linked_limits = [
        reward_values(category_rewards[cat], exclude)[1] for cat in linked_ready
    ]
    limits = dict(linked_limits[0])

    extra_count, remaining_extra = generate_extra_queues(
        guild_id,
        extra_pool,
        limits,
        linked_next_queue_no,
    )

    summary.update(
        extra_count=extra_count,
        extra_start=linked_next_queue_no,
        extra_end=linked_next_queue_no + extra_count - 1,
        remaining_extra=remaining_extra,
        extra_limits_from=linked_ready[0],
        linked_limits_differ=any(other != limits for other in linked_limits[1:]),
    )

    return summary
