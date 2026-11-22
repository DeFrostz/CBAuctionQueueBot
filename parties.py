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
from generator import (
    build_extra_pool,
    check_categories,
    count_extra_queues,
    get_queue_count_from_rewards,
    reward_values,
)


def party_of(queue_no, queue_start, party_count):
    """Party (1..party_count) that owns the given queue number."""
    return (queue_start - 1 + queue_no - 1) % party_count + 1


def next_party(party, party_count):
    return party % party_count + 1


def effective_queue_start(plan):
    """
    Party of queue 1 for the queues that exist right now.

    It is the value used at /generate time, so labels stay correct after
    /endday has already moved the plan on to tomorrow.
    """
    used = plan["used_queue_start"]
    return used if used is not None else plan["queue_start"]


def party_label(queue_no, plan):
    """'P5' style label for a linked queue, or None when no plan is set."""
    if plan is None:
        return None
    return f"P{party_of(queue_no, effective_queue_start(plan), plan['party_count'])}"


# -------------------------
# Card placement (pure: no database access)
# -------------------------


def place_cards(cards, last_queue, queue_start, count, card_start):
    """
    Give each Card to a queue, following the party rotation.

    cards: [(category, page, slot)] in hand-out order.
    Returns (placements, unassigned) where each placement is
    (category, page, slot, queue_no, party).

    The first Card goes to the first queue of `card_start`. Every next Card
    goes to the next party, on the first free queue after the previous Card
    (wrapping to the top of the list when needed). Normally that is just the
    next queue; it only jumps back when the rotation wraps past the last
    queue of the day.
    """

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
    placements = []
    previous_queue = 0
    party = card_start

    for category, page, slot in cards:
        queue_no = queue_for(party, previous_queue, used)
        if queue_no is None:
            break

        used.add(queue_no)
        placements.append((category, page, slot, queue_no, party))
        previous_queue = queue_no
        party = next_party(party, count)

    return placements, len(cards) - len(placements)


def summarize_placements(placements):
    """Per-category summary used by the /generate message."""
    per_category = {}
    for category, _page, _slot, queue_no, party in placements:
        info = per_category.setdefault(
            category, {"count": 0, "queues": [], "parties": []}
        )
        info["count"] += 1
        info["queues"].append(queue_no)
        info["parties"].append(party)
    return per_category


def assign_cards(guild_id, plan, categories):
    """
    Place the remaining Cards of `categories` in the saved queues.

    Only categories whose Card limit is 0 are handled (otherwise Cards are
    already inside the normal queues).
    """
    count = plan["party_count"]
    queue_start = effective_queue_start(plan)
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

    placements, unassigned = place_cards(
        cards, last_queue, queue_start, count, card_start
    )

    result["per_category"] = summarize_placements(placements)
    result["unassigned"] = unassigned
    result["start_missing"] = not placements
    if placements:
        result["last_party"] = placements[-1][4]
        save_queue_positions_bulk(
            [
                (guild_id, category, queue_no, "CARD", page, slot)
                for category, page, slot, queue_no, _party in placements
            ]
        )

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
    queue_start = effective_queue_start(plan)

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


# -------------------------
# Quick calculation for /partyplan (reads the config, writes nothing)
# -------------------------


def _chunk_blocks(title, lines, limit=1800):
    """Split lines into code blocks that fit a Discord message."""
    blocks = []
    current = [title]
    size = len(title)
    for line in lines:
        if size + len(line) + 1 > limit and len(current) > 1:
            blocks.append("```\n" + "\n".join(current) + "\n```")
            current = [title + " (continued)"]
            size = len(current[0])
        current.append(line)
        size += len(line) + 1
    blocks.append("```\n" + "\n".join(current) + "\n```")
    return blocks


SHORT_NAMES = {"Guild League": "GL", "League Prize": "LP"}


def render_party_views(
    last_queue, cards_by_queue, queue_start, count, view, header, inline_cards=()
):
    """
    Text messages for the party plan.

    cards_by_queue: {queue_no: [(category, page, slot)]}
    view: "queue" (queue - party table), "card" (Card per party) or "both".
    inline_cards: categories whose Cards are already inside the normal queues.
    """
    width = max(2, len(str(last_queue)))
    messages = []

    def add_section(blocks):
        # Every section starts with the heading, like the hand-made posts.
        if header:
            blocks[0] = header + "\n" + blocks[0]
        messages.extend(blocks)

    if view in ("card", "both"):
        lines = []
        for category in LINKED:
            lines.append(category)
            own = sorted(
                (page, slot, q)
                for q, items in cards_by_queue.items()
                for cat, page, slot in items
                if cat == category
            )
            if category in inline_cards:
                lines.append("(Card is inside the normal queues)")
            elif not own:
                lines.append("(no Card)")
            for page, slot, q in own:
                lines.append(
                    f"Page {page} - slot {slot} : P{party_of(q, queue_start, count)}"
                )
            lines.append("")
        add_section(_chunk_blocks("Card", lines[:-1]))

    if view in ("queue", "both"):
        lines = []
        for q in range(1, last_queue + 1):
            text = f"{q:0{width}d} - P{party_of(q, queue_start, count)}"
            for category, page, slot in sorted(cards_by_queue.get(q, [])):
                text += (
                    f" + Card {SHORT_NAMES.get(category, category)}"
                    f" Page {page} - slot {slot}"
                )
            lines.append(text)
        add_section(_chunk_blocks("queue - party", lines))

    return messages


def preview_party_plan(guild_id, plan, view, header):
    """
    Work out what /generate would give right now, without saving anything.

    Uses the saved stock / limits and the party plan. Returns a dict with
    "messages" (text to post) and "notes" (private remarks), or an "error".
    """
    ready, skipped = check_categories(guild_id, LINKED)
    notes = [f"{category}: skipped ({reason})" for category, reason in skipped]

    if not ready:
        return {"error": "not_ready", "notes": notes}

    counts = {
        category: get_queue_count_from_rewards(rows)
        for category, rows in ready.items()
    }

    # Same rule as /generate: leftovers of both categories form Extra queues.
    extra_pool = build_extra_pool(ready, counts)
    first_rows = next(iter(ready.values()))
    _stocks, limits = reward_values(first_rows)
    extra_count = count_extra_queues(extra_pool, limits)

    last_queue = sum(counts.values()) + extra_count
    if last_queue == 0:
        return {"error": "no_queues", "notes": notes}

    cards = []
    inline = []
    for category, rows in ready.items():
        stocks, card_limits = reward_values(rows)
        if card_limits["CARD"] > 0:
            inline.append(category)
            continue
        for index in range(stocks["CARD"]):
            page, slot = position(index)
            cards.append((category, page, slot))

    count = plan["party_count"]
    queue_start = plan["queue_start"]

    placements, unassigned = place_cards(
        cards, last_queue, queue_start, count, plan["card_start"]
    )

    cards_by_queue = {}
    for category, page, slot, queue_no, _party in placements:
        cards_by_queue.setdefault(queue_no, []).append((category, page, slot))

    if unassigned:
        notes.append(
            f"{unassigned} Card(s) do not fit in today's queues and are left out."
        )
    for category in inline:
        notes.append(
            f"{category}: Card limit is above 0, so its Cards are inside the "
            "normal queues and are not listed per party."
        )
    notes.append(
        f"{last_queue} queues. Preview only, nothing was saved. "
        "Use /generate to create them."
    )

    return {
        "messages": render_party_views(
            last_queue, cards_by_queue, queue_start, count, view, header, inline
        ),
        "notes": notes,
    }
