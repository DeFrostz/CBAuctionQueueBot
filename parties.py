"""Party plan for Guild League / League Prize.

Each linked queue belongs to a party. Parties form a circle (P1..Pn):
queue 1 is `queue_start`, queue 2 the next party, and so on, wrapping after
the last party. The queue where the day ends decides where tomorrow starts.

Card and Astrocore are "spread" rewards. Feathers decide how many queues
there are; a spread reward is then handed out like this:

  * base      = pool / queues, rounded down (never above the limit per queue).
                Every queue gets the same base.
  * remainder = what is left. It is handed out as +1 to some queues, one per
                queue, following the party rotation from the group's start
                party (Card and Astrocore each have their own pointer).
                A pool smaller than the number of queues is just the case
                with base 0.
  * the party of the last +1 decides where tomorrow's rotation starts.

Guild League items come first, then League Prize. The four Astrocore kinds
move together (same queues), so a party gets a complete set.
"""

from constants import (
    LINKED,
    REWARD_NAMES,
    SPREAD_GROUPS,
    SPREAD_REWARDS,
    list_offset,
    position,
)
from database import (
    get_max_queue_no,
    get_party_plan,
    get_rewards,
    save_queue_positions_bulk,
    set_last_spread_parties,
    update_party_pointers,
)
from generator import (
    build_extra_pool,
    check_categories,
    count_extra_queues,
    get_queue_count_from_rewards,
    reward_values,
)

SHORT_NAMES = {"Guild League": "GL", "League Prize": "LP"}
GROUP_TITLES = {"card": "Card", "astro": "Astrocore"}


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


def group_start(plan, group):
    """Party where the rotation of a spread group starts today."""
    if group == "astro" and plan["astro_start"] is not None:
        return plan["astro_start"]
    return plan["card_start"]


def party_label(queue_no, plan):
    """'P5' style label for a linked queue, or None when no plan is set."""
    if plan is None:
        return None
    return f"P{party_of(queue_no, effective_queue_start(plan), plan['party_count'])}"


def kind_name(reward):
    """Display name without the emoji, e.g. 'Guardian Starcore'."""
    return REWARD_NAMES[reward].split(" ", 1)[1]


def compress_parties(parties, count):
    """[11, 12, 13, 14] -> 'P11-P14'; follows the rotation (16 -> 1)."""
    if not parties:
        return ""
    runs = []
    start = previous = parties[0]
    for party in parties[1:]:
        if party == next_party(previous, count):
            previous = party
            continue
        runs.append((start, previous))
        start = previous = party
    runs.append((start, previous))
    return ", ".join(
        f"P{a}" if a == b else f"P{a}-P{b}" for a, b in runs
    )


# -------------------------
# Spread calculation (pure: no database access)
# -------------------------


def rotation_order(n, last_queue, queue_start, count, start_party):
    """
    Up to `n` queues in party-rotation order.

    The first queue is the first queue of `start_party`. Every next queue
    belongs to the next party: the first free queue of that party after the
    previous one, wrapping to the top of the list. A party without a free
    queue is skipped.
    """
    parties = {
        q: party_of(q, queue_start, count) for q in range(1, last_queue + 1)
    }
    used = set()
    order = []
    previous = 0
    party = start_party
    misses = 0

    while len(order) < n and misses < count:
        candidates = list(range(previous + 1, last_queue + 1)) + list(
            range(1, previous + 1)
        )
        queue_no = next(
            (q for q in candidates if q not in used and parties[q] == party),
            None,
        )
        if queue_no is None:
            party = next_party(party, count)
            misses += 1
            continue

        used.add(queue_no)
        order.append(queue_no)
        previous = queue_no
        party = next_party(party, count)
        misses = 0

    return order


def compute_spread(ready, last_queue, queue_start, count, starts):
    """
    Work out where every Card / Astrocore goes.

    ready: {category: reward rows}, linked categories in order.
    starts: {"card": party, "astro": party} rotation start of each group.

    Returns {"rewards": {reward: {...}}, "groups": {group: {...}}}.
    Each reward has total, cap, per_queue (base), bonus (+1 queues), left
    and assignments {queue_no: [(category, page, slot)]}.
    """
    rewards_out = {}
    groups_out = {}

    for group, rewards in SPREAD_GROUPS.items():
        start_party = starts[group]
        order = rotation_order(last_queue, last_queue, queue_start, count, start_party)
        bonus_allowed = bool(order)

        # Queues the rotation could not reach still get the base.
        everyone = order + [q for q in range(1, last_queue + 1) if q not in order]

        max_bonus = 0

        for reward in rewards:
            pool = []
            cap = None
            for category, rows in ready.items():
                stocks, limits = reward_values(rows)
                if cap is None:
                    cap = limits[reward]
                offset = list_offset(reward, stocks)
                for index in range(stocks[reward]):
                    page, slot = position(offset + index)
                    pool.append((category, page, slot))

            total = len(pool)
            cap = cap or 0  # 0 = no limit per queue

            base = total // last_queue if last_queue else 0
            if cap > 0:
                base = min(base, cap)
            remainder = total - base * last_queue

            bonus = 0
            if remainder > 0 and bonus_allowed and (cap == 0 or base + 1 <= cap):
                bonus = min(remainder, len(order))
            left = remainder - bonus

            assignments = {}
            taken = 0
            for index, queue_no in enumerate(everyone):
                amount = base + (1 if index < bonus else 0)
                if amount:
                    assignments[queue_no] = pool[taken : taken + amount]
                    taken += amount

            rewards_out[reward] = {
                "total": total,
                "cap": cap,
                "per_queue": base,
                "bonus": bonus,
                "left": left,
                "assignments": assignments,
            }
            max_bonus = max(max_bonus, bonus)

        bonus_parties = [
            party_of(q, queue_start, count) for q in order[:max_bonus]
        ]
        groups_out[group] = {
            "start_party": start_party,
            "first_party": party_of(order[0], queue_start, count) if order else None,
            "bonus_parties": bonus_parties,
            "last_party": bonus_parties[-1] if bonus_parties else None,
        }

    return {"rewards": rewards_out, "groups": groups_out}


def spread_summary_lines(spread, count):
    """Text lines describing a compute_spread result."""
    lines = []

    for group, rewards in SPREAD_GROUPS.items():
        info = spread["groups"][group]
        shown = [spread["rewards"][r] for r in rewards]
        if all(item["total"] == 0 for item in shown):
            continue

        signature = {(i["per_queue"], i["bonus"], i["left"], i["total"]) for i in shown}
        if len(signature) == 1:
            entries = [(GROUP_TITLES[group], shown[0])]
        else:
            entries = [
                (kind_name(r) if group == "astro" else GROUP_TITLES[group], spread["rewards"][r])
                for r in rewards
            ]

        for title, item in entries:
            parts = [f"{item['per_queue']} per queue"]
            if item["bonus"] > 0:
                parts.append(
                    f"+1 on {item['bonus']} queue(s) "
                    f"({compress_parties(info['bonus_parties'][: item['bonus']], count)})"
                )
            if item["left"] > 0:
                parts.append(f"{item['left']} left over")
            lines.append(f"- {title}: " + ", ".join(parts))

        if info["first_party"] is not None and info["first_party"] != info["start_party"]:
            lines.append(
                f"⚠️ {GROUP_TITLES[group]}: P{info['start_party']} has no queue "
                f"today, rotation started at P{info['first_party']}."
            )

    return lines


# -------------------------
# Saved queues: place the spread rewards and move to the next day
# -------------------------


def assign_spread(guild_id, plan, categories):
    """
    Place Card / Astrocore of `categories` in the saved queues.

    The pointers' "last +1 party" are stored so /endday can move them.
    """
    count = plan["party_count"]
    queue_start = effective_queue_start(plan)
    last_queue = get_max_queue_no(guild_id, LINKED)

    ready = {category: get_rewards(guild_id, category) for category in categories}

    spread = compute_spread(
        ready,
        last_queue,
        queue_start,
        count,
        {"card": group_start(plan, "card"), "astro": group_start(plan, "astro")},
    )

    rows = []
    for reward, item in spread["rewards"].items():
        for queue_no, entries in item["assignments"].items():
            for category, page, slot in entries:
                rows.append((guild_id, category, queue_no, reward, page, slot))

    save_queue_positions_bulk(rows)

    set_last_spread_parties(
        guild_id,
        spread["groups"]["card"]["last_party"],
        spread["groups"]["astro"]["last_party"],
    )

    return spread


def end_day(guild_id):
    """
    Move the pointers to where tomorrow starts.

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

    def moved(last, current):
        return next_party(last, count) if last is not None else current

    new_card_start = moved(plan["last_card_party"], group_start(plan, "card"))
    new_astro_start = moved(plan["last_astro_party"], group_start(plan, "astro"))

    update_party_pointers(guild_id, new_queue_start, new_card_start, new_astro_start, 1)

    return {
        "last_queue": last_queue,
        "last_party": last_party,
        "last_card_party": plan["last_card_party"],
        "last_astro_party": plan["last_astro_party"],
        "new_queue_start": new_queue_start,
        "new_card_start": new_card_start,
        "new_astro_start": new_astro_start,
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


def _items_by_category(assignments, queue_start, count):
    """{category: [(page, slot, party)]} sorted by page and slot."""
    result = {category: [] for category in LINKED}
    for queue_no, entries in assignments.items():
        party = party_of(queue_no, queue_start, count)
        for category, page, slot in entries:
            result.setdefault(category, []).append((page, slot, party))
    for items in result.values():
        items.sort()
    return result


def render_party_views(last_queue, spread, queue_start, count, view, header):
    """
    Text messages for the party plan.

    view: "queue" (queue - party table), "card", "astro" or "both" (all).
    """
    rewards = spread["rewards"]
    width = max(2, len(str(last_queue)))
    messages = []

    def add_section(blocks):
        # Every section starts with the heading, like the hand-made posts.
        if header:
            blocks[0] = header + "\n" + blocks[0]
        messages.extend(blocks)

    if view in ("card", "both"):
        lines = []
        items = _items_by_category(rewards["CARD"]["assignments"], queue_start, count)
        for category in LINKED:
            lines.append(category)
            if not items[category]:
                lines.append("(no Card)")
            for page, slot, party in items[category]:
                lines.append(f"Page {page} - slot {slot} : P{party}")
            lines.append("")
        add_section(_chunk_blocks("Card", lines[:-1]))

    if view in ("astro", "both"):
        lines = []
        for reward in SPREAD_GROUPS["astro"]:
            items = _items_by_category(rewards[reward]["assignments"], queue_start, count)
            if not any(items.values()):
                continue
            lines.append(kind_name(reward))
            for category in LINKED:
                if not items[category]:
                    continue
                lines.append(f"{category}")
                for page, slot, party in items[category]:
                    lines.append(f"Page {page} - slot {slot} : P{party}")
            lines.append("")
        if lines:
            add_section(_chunk_blocks("Astrocore", lines[:-1]))

    if view in ("queue", "both"):
        lines = []
        card = rewards["CARD"]["assignments"]
        for q in range(1, last_queue + 1):
            text = f"{q:0{width}d} - P{party_of(q, queue_start, count)}"
            for category, page, slot in card.get(q, []):
                text += (
                    f" + Card {SHORT_NAMES.get(category, category)}"
                    f" Page {page} - slot {slot}"
                )
            sets = max(
                (len(rewards[r]["assignments"].get(q, [])) for r in SPREAD_GROUPS["astro"]),
                default=0,
            )
            if sets:
                text += f" + Astro x{sets}"
            lines.append(text)
        add_section(_chunk_blocks("queue - party", lines))

    return messages


def preview_party_plan(guild_id, plan, view, header):
    """
    Work out what /generate would give right now, without saving anything.

    Uses the saved stock / limits and the party plan. Returns a dict with
    "messages" (text to post) and "notes" (private remarks), or an "error".
    """
    ready, skipped = check_categories(guild_id, LINKED, SPREAD_REWARDS)
    notes = [f"{category}: skipped ({reason})" for category, reason in skipped]

    if not ready:
        return {"error": "not_ready", "notes": notes}

    counts = {
        category: get_queue_count_from_rewards(rows, SPREAD_REWARDS)
        for category, rows in ready.items()
    }

    # Same rule as /generate: leftovers of both categories form Extra queues.
    extra_pool = build_extra_pool(ready, counts, SPREAD_REWARDS)
    _stocks, limits = reward_values(next(iter(ready.values())), SPREAD_REWARDS)
    extra_count = count_extra_queues(extra_pool, limits)

    last_queue = sum(counts.values()) + extra_count
    if last_queue == 0:
        return {"error": "no_queues", "notes": notes}

    count = plan["party_count"]
    queue_start = plan["queue_start"]

    spread = compute_spread(
        ready,
        last_queue,
        queue_start,
        count,
        {"card": group_start(plan, "card"), "astro": group_start(plan, "astro")},
    )

    notes.append(
        f"{last_queue} queues. Preview only, nothing was saved. "
        "Use /generate to create them."
    )
    notes.extend(spread_summary_lines(spread, count))

    return {
        "messages": render_party_views(
            last_queue, spread, queue_start, count, view, header
        ),
        "notes": notes,
    }
