"""Party plan for Guild League / League Prize.

Each linked queue belongs to a party. Parties form a circle (P1..Pn):
queue 1 is `queue_start`, queue 2 the next party, and so on, wrapping after
the last party. The queue where the day ends decides where tomorrow starts.

Cards are handed out one per party in rotation order, starting at the first
queue whose party is `card_start`: each next Card goes to the next party
(P13, P14, ... wrapping after the last party), on the queue where that party
sits today. Guild League cards come first, then League Prize. The party of the
last Card decides where tomorrow's cards start.
"""

from constants import LINKED, position
from database import (
    get_assigned_count,
    get_max_queue_no,
    get_party_plan,
    get_rewards,
    save_queue_positions_bulk,
    set_last_card_party,
    update_party_pointers,
)


def party_of(queue_no, queue_start, party_count):
    """Party (1..party_count) that owns the given queue number."""
    return (queue_start - 1 + queue_no - 1) % party_count + 1


def next_party(party, party_count):
    return party % party_count + 1


def party_label(queue_no, plan):
    """'P5' style label for a linked queue, or None when no plan is set."""
    if plan is None:
        return None
    return f"P{party_of(queue_no, plan['queue_start'], plan['party_count'])}"


def assign_cards(guild_id, plan, categories):
    """
    Place the remaining Cards of `categories`, one per queue, following the
    party rotation.

    The first Card goes to the first queue of `card_start`. Every next Card
    goes to the next party, on the first free queue after the previous Card
    (wrapping to the top of the list when needed). Normally that is just the
    next queue; it only jumps back when the rotation wraps past the last
    queue of the day.

    Only categories whose Card limit is 0 are handled (otherwise Cards are
    already inside the normal queues).
    """
    count = plan["party_count"]
    queue_start = plan["queue_start"]
    card_start = plan["card_start"]
    last_queue = get_max_queue_no(guild_id, LINKED)

    result = {
        "per_category": {},
        "unassigned": 0,
        "start_missing": False,
        "limit_skipped": [],
        "last_party": None,
    }

    cards = []  # (category, page, slot) in hand-out order
    for category in categories:
        rows = {r["reward_type"]: r for r in get_rewards(guild_id, category)}
        row = rows.get("CARD")
        if row is None:
            continue
        if int(row["limit_per_queue"]) > 0:
            result["limit_skipped"].append(category)
            continue

        stock = int(row["stock"])
        assigned = get_assigned_count(guild_id, category, "CARD")
        for index in range(assigned, stock):
            page, slot = position(index)
            cards.append((category, page, slot))

    if not cards:
        set_last_card_party(guild_id, None)
        return result

    def queue_for(party, after_queue, used):
        """First unused queue of `party` after `after_queue`, wrapping."""
        order = list(range(after_queue + 1, last_queue + 1)) + list(
            range(1, after_queue + 1)
        )
        for q in order:
            if q not in used and party_of(q, queue_start, count) == party:
                return q
        return None

    used = set()
    rows_to_save = []
    previous_queue = 0
    party = card_start

    for category, page, slot in cards:
        queue_no = queue_for(party, previous_queue, used)
        if queue_no is None:
            break

        used.add(queue_no)
        rows_to_save.append((guild_id, category, queue_no, "CARD", page, slot))

        info = result["per_category"].setdefault(
            category,
            {"count": 0, "queues": [], "parties": []},
        )
        info["count"] += 1
        info["queues"].append(queue_no)
        info["parties"].append(party)

        result["last_party"] = party
        previous_queue = queue_no
        party = next_party(party, count)

    placed = len(rows_to_save)
    result["unassigned"] = len(cards) - placed
    result["start_missing"] = placed == 0

    if rows_to_save:
        save_queue_positions_bulk(rows_to_save)

    set_last_card_party(guild_id, result["last_party"])

    return result


def card_summary_lines(result):
    """Text lines describing what assign_cards did."""
    lines = []

    if result["start_missing"]:
        lines.append(
            "⚠️ The Card start party does not appear in today's queues, "
            "so no Card was placed."
        )
        return lines

    for category, info in result["per_category"].items():
        queues = info["queues"]
        parties_ = info["parties"]
        consecutive = all(
            queues[i + 1] == queues[i] + 1 for i in range(len(queues) - 1)
        )
        if consecutive:
            where = (
                f"Queue {queues[0]}-{queues[-1]} · "
                f"P{parties_[0]}-P{parties_[-1]}"
            )
        else:
            where = "Queue " + ", ".join(
                f"{q} (P{p})" for q, p in zip(queues, parties_)
            )
        lines.append(f"- {category}: {info['count']} ({where})")

    if result["unassigned"] > 0:
        lines.append(
            f"⚠️ {result['unassigned']} Card(s) did not fit in the remaining "
            "queues and were left unassigned."
        )

    for category in result["limit_skipped"]:
        lines.append(
            f"ℹ️ {category}: Card limit is above 0, so Cards are already "
            "inside the queues."
        )

    return lines


def end_day(guild_id):
    """
    Move both pointers to where tomorrow starts.

    Returns a dict. On failure it has an "error" key:
    "no_plan", "closed" or "no_queues".
    """
    plan = get_party_plan(guild_id)
    if plan is None:
        return {"error": "no_plan"}
    if plan["day_closed"]:
        return {"error": "closed"}

    last_queue = get_max_queue_no(guild_id, LINKED)
    if last_queue == 0:
        return {"error": "no_queues"}

    count = plan["party_count"]
    queue_start = plan["queue_start"]

    last_party = party_of(last_queue, queue_start, count)
    new_queue_start = next_party(last_party, count)

    last_card_party = plan["last_card_party"]
    if last_card_party is not None:
        new_card_start = next_party(last_card_party, count)
    else:
        new_card_start = plan["card_start"]

    update_party_pointers(guild_id, new_queue_start, new_card_start, 1)

    return {
        "last_queue": last_queue,
        "last_party": last_party,
        "last_card_party": last_card_party,
        "new_queue_start": new_queue_start,
        "new_card_start": new_card_start,
    }
