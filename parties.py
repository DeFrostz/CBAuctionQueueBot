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
    EMPERIUM_CATEGORY,
    EMPERIUM_TABLE,
    LINKED,
    RANK_TABLE,
    REWARD_NAMES,
    SPREAD_GROUPS,
    SPREAD_REWARDS,
    emperium_rank_values,
    list_offset,
    position,
    rank_values,
)
from database import (
    get_max_queue_no,
    get_assigned_count,
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
SCOPE_CATEGORIES = {"linked": LINKED, "emperium": (EMPERIUM_CATEGORY,)}
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


def end_day(guild_id, scope="linked"):
    """
    Move the pointers to where tomorrow starts.

    scope: "linked" (Guild League / League Prize) or "emperium".
    Returns a dict. On failure it has an "error" key:
    "no_plan", "closed" or "no_queues".
    """
    plan = get_party_plan(guild_id, scope)
    if plan is None:
        return {"error": "no_plan"}
    if plan["day_closed"]:
        return {"error": "closed"}

    last_queue = get_max_queue_no(guild_id, SCOPE_CATEGORIES[scope])
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

    update_party_pointers(
        guild_id, new_queue_start, new_card_start, new_astro_start, 1, scope
    )

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
                text += f" + Astrocore {sets} {'set' if sets == 1 else 'sets'} (4 ประเภท)"
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

    if all(
        spread["rewards"][reward]["total"] == 0
        for reward in SPREAD_GROUPS["astro"]
    ):
        notes.append(
            "Astrocore: no stock is set for Guild League / League Prize, so it is "
            "not shown. Use /setrank, or the Astrocore fields of /setallstock."
        )

    return {
        "messages": render_party_views(
            last_queue, spread, queue_start, count, view, header
        ),
        "notes": notes,
    }


def build_party_note(guild_id, plan, date, scope="linked"):
    """
    Short note about where today's rotation ended, or None without queues.

    Reads the generated queues and the "last +1" parties saved by /generate,
    so it still describes the same day after /endday. When a reward had no
    +1 today, the latest separated party is still the one from the days
    before: the party right before today's rotation start.
    """
    categories = SCOPE_CATEGORIES[scope]
    last_queue = get_max_queue_no(guild_id, categories)
    if last_queue == 0:
        return None

    count = plan["party_count"]
    queue_start = effective_queue_start(plan)

    def has_stock(group):
        return any(
            int(row["stock"]) > 0
            for category in categories
            for row in get_rewards(guild_id, category)
            if row["reward_type"] in SPREAD_GROUPS[group]
        )

    def latest(group, last_party):
        if last_party is not None:
            return f"P{last_party}"
        if not has_stock(group):
            return "-"
        # The rotation starts right after the last +1 of the day before.
        start = group_start(plan, group)
        return f"P{(start - 2) % count + 1}"

    title = f"Note {date}" + (" Emperium" if scope == "emperium" else "")
    lines = [
        title,
        f"Lastest Seperated Queue Card  : {latest('card', plan['last_card_party'])}",
        f"Lastest Seperated Queue Astrocore : {latest('astro', plan['last_astro_party'])}",
        f"Lastest Normal Queue Count : P{party_of(last_queue, queue_start, count)}",
    ]
    return "```\n" + "\n".join(lines) + "\n```"

# -------------------------
# Emperium Overrun
# -------------------------
#
# Same party rotation as Guild League, but with its own plan. Feathers decide
# the queues. Card and Astrocore: every queue gets pool // queues (never above
# the limit); what is left ("Extra After Calculate") is not tied to a queue:
# one item per party along the party rotation, from the group's own pointer.


def _emperium_rows(values):
    """Reward rows (dicts) built from a rank's {reward: (stock, limit)}."""
    return [
        {
            "category": EMPERIUM_CATEGORY,
            "reward_type": reward,
            "stock": stock,
            "limit_per_queue": limit,
        }
        for reward, (stock, limit) in values.items()
    ]


def emperium_outcome(rows, queue_start, count, starts):
    """
    Work out one Emperium day (pure: nothing is read or saved).

    rows: reward rows of Emperium Overrun. starts: {"card": party, "astro": party}
    where each Extra rotation starts. Returns None when no queue can be made.
    """
    queues = get_queue_count_from_rewards(rows, SPREAD_REWARDS)
    if queues == 0:
        return None

    stocks, limits = reward_values(rows)

    feather_left = {
        reward: stocks[reward] - queues * limits[reward]
        for reward in ("FEATHER_S", "FEATHER_A")
    }

    rewards_out = {}
    groups_out = {}

    for group, rewards in SPREAD_GROUPS.items():
        start_party = starts[group]
        max_extra = 0

        for reward in rewards:
            total = stocks[reward]
            cap = limits[reward]  # 0 = no limit per queue
            base = total // queues
            if cap > 0:
                base = min(base, cap)
            extra = total - base * queues

            offset = list_offset(reward, stocks)
            pool = [position(offset + index) for index in range(total)]

            assignments = {}
            if base:
                for queue_no in range(1, queues + 1):
                    start = (queue_no - 1) * base
                    assignments[queue_no] = [
                        (EMPERIUM_CATEGORY, page, slot)
                        for page, slot in pool[start : start + base]
                    ]

            extra_items = []
            for index, (page, slot) in enumerate(pool[queues * base :]):
                party = (start_party - 1 + index) % count + 1
                extra_items.append((page, slot, party))

            rewards_out[reward] = {
                "total": total,
                "cap": cap,
                "per_queue": base,
                "extra": extra,
                "assignments": assignments,
                "extra_items": extra_items,
            }
            max_extra = max(max_extra, extra)

        groups_out[group] = {
            "start_party": start_party,
            "extra": max_extra,
            "last_party": (
                (start_party - 1 + max_extra - 1) % count + 1 if max_extra else None
            ),
        }

    return {
        "queues": queues,
        "limits": limits,
        "feather_left": feather_left,
        "rewards": rewards_out,
        "groups": groups_out,
    }


def assign_emperium(guild_id, plan):
    """Save the base Card / Astrocore rows of the generated Emperium queues."""
    rows = get_rewards(guild_id, EMPERIUM_CATEGORY)
    outcome = emperium_outcome(
        rows,
        effective_queue_start(plan),
        plan["party_count"],
        {"card": group_start(plan, "card"), "astro": group_start(plan, "astro")},
    )
    if outcome is None:
        set_last_spread_parties(guild_id, None, None, "emperium")
        return None

    save_queue_positions_bulk(
        [
            (guild_id, category, queue_no, reward, page, slot)
            for reward, item in outcome["rewards"].items()
            for queue_no, entries in item["assignments"].items()
            for category, page, slot in entries
        ]
    )

    set_last_spread_parties(
        guild_id,
        outcome["groups"]["card"]["last_party"],
        outcome["groups"]["astro"]["last_party"],
        "emperium",
    )
    return outcome


def emperium_summary_lines(outcome, count):
    """Text lines describing an emperium_outcome for the /generate message."""
    lines = []

    for group, rewards in SPREAD_GROUPS.items():
        info = outcome["groups"][group]
        shown = [outcome["rewards"][r] for r in rewards]
        if all(item["total"] == 0 for item in shown):
            continue

        signature = {(i["per_queue"], i["extra"], i["total"]) for i in shown}
        if len(signature) == 1:
            entries = [(GROUP_TITLES[group], shown[0])]
        else:
            entries = [
                (kind_name(r) if group == "astro" else GROUP_TITLES[group], outcome["rewards"][r])
                for r in rewards
            ]

        for title, item in entries:
            parts = [f"{item['per_queue']} per queue"]
            if item["extra"] > 0:
                parties = [party for _page, _slot, party in item["extra_items"]]
                parts.append(
                    f"{item['extra']} extra to parties {compress_parties(parties, count)}"
                )
            lines.append(f"- {title}: " + ", ".join(parts))

    left = outcome["feather_left"]
    for reward, amount in left.items():
        if amount > 0:
            lines.append(f"- {REWARD_NAMES[reward]} left over: {amount}")

    return lines


def _astro_extra_lines(items, legend=True):
    """
    Compact Astrocore extras: one line per party with the four kinds
    ("p9 : GC 3-3 | DC 7-3 | GS 11-3 | DS 15-3", page-slot each).

    items: {reward: [(page, slot, party)]}
    """
    kinds = list(SPREAD_GROUPS["astro"])
    abbreviations = {reward: reward.split("_")[1] for reward in kinds}
    lines = []
    if legend:
        lines.append(" / ".join(f"{abbreviations[r]} {kind_name(r)}" for r in kinds))

    rows = max((len(items.get(r, [])) for r in kinds), default=0)
    if rows == 0:
        return lines

    width = max(
        len(f"p{party}")
        for r in kinds
        for _page, _slot, party in items.get(r, [])
    )
    for index in range(rows):
        party = next(
            items[r][index][2] for r in kinds if index < len(items.get(r, []))
        )
        cells = [
            f"{abbreviations[r]} {items[r][index][0]}-{items[r][index][1]}"
            if index < len(items.get(r, []))
            else f"{abbreviations[r]} -"
            for r in kinds
        ]
        lines.append(f"{f'p{party}'.ljust(width)} : " + " | ".join(cells))
    return lines


def emperium_extras(guild_id, plan):
    """
    Extra Card / Astrocore of the generated Emperium queues, with parties.

    Rebuilt from what was saved: the items no queue holds are the extras, and
    the party of the last extra (kept until the next /generate) tells where
    the rotation started. Returns {reward: [(page, slot, party)]}, empty when
    there are no extras.
    """
    if plan is None:
        return {}
    rows = get_rewards(guild_id, EMPERIUM_CATEGORY)
    if not rows:
        return {}

    stocks, _limits = reward_values(rows)
    count = plan["party_count"]
    result = {}

    for group, rewards in SPREAD_GROUPS.items():
        last = plan["last_card_party"] if group == "card" else plan["last_astro_party"]
        assigned = {
            r: get_assigned_count(guild_id, EMPERIUM_CATEGORY, r) for r in rewards
        }
        extra = {r: max(stocks[r] - assigned[r], 0) for r in rewards}
        biggest = max(extra.values())
        if last is None or biggest == 0:
            continue

        start = (last - 1 - (biggest - 1)) % count + 1
        for reward in rewards:
            offset = list_offset(reward, stocks)
            items = []
            for k in range(extra[reward]):
                page, slot = position(offset + assigned[reward] + k)
                items.append((page, slot, (start - 1 + k) % count + 1))
            if items:
                result[reward] = items

    return result


def party_extra_lines(extras, party):
    """Lines for the extras one party gets (empty when it gets none)."""
    lines = []
    for page, slot, owner in extras.get("CARD", []):
        if owner == party:
            lines.append(f"Card : Page {page} : Slot {slot}")

    mine = {
        reward: [item for item in extras.get(reward, []) if item[2] == party]
        for reward in SPREAD_GROUPS["astro"]
    }
    for text in _astro_extra_lines(mine, legend=False):
        lines.append("Astrocore : " + text.split(" : ", 1)[1])
    return lines


def extra_overview_lines(extras):
    """Every extra by party, in the same format as the /emperiumplan note."""
    lines = []

    card = extras.get("CARD", [])
    if card:
        width = max(len(f"p{party}") for _page, _slot, party in card)
        lines.append(f"Card {len(card)}")
        for page, slot, party in card:
            lines.append(f"{f'p{party}'.ljust(width)} : Page {page} Slot {slot}")

    astro = {r: extras.get(r, []) for r in SPREAD_GROUPS["astro"]}
    sets = max((len(v) for v in astro.values()), default=0)
    if sets:
        if lines:
            lines.append("")
        lines.append(
            f"Astrocore {sets} {'set' if sets == 1 else 'sets'} (4 ประเภท)"
        )
        lines.extend(_astro_extra_lines(astro))

    return lines


def _emperium_signature(outcome, include_card, include_astro):
    """What makes two ranks look the same in the posted note."""
    parts = [outcome["queues"], tuple(outcome["feather_left"].values())]
    if include_card:
        parts.append(
            tuple(
                (page, slot)
                for page, slot, _party in outcome["rewards"]["CARD"]["extra_items"]
            )
        )
    if include_astro:
        parts.append(
            tuple(
                tuple(
                    (page, slot)
                    for page, slot, _party in outcome["rewards"][reward]["extra_items"]
                )
                for reward in SPREAD_GROUPS["astro"]
            )
        )
    return tuple(parts)


def build_emperium_plan_messages(league, queue_start, count, starts, view, date):
    """
    The Emperium note for every rank of a league, ranks that look the same
    grouped together ("Condition Rank 4 5 6").

    view: "all" (Card and Astrocore), "card" or "astro".
    Nothing is read from or written to the database.
    """
    include_card = view in ("all", "card")
    include_astro = view in ("all", "astro")

    outcomes = {}
    for rank in range(1, len(EMPERIUM_TABLE[league]) + 1):
        values = emperium_rank_values(league, rank)
        outcome = emperium_outcome(_emperium_rows(values), queue_start, count, starts)
        if outcome is not None:
            outcomes[rank] = outcome

    groups = []  # [signature, [ranks]]
    for rank, outcome in outcomes.items():
        signature = _emperium_signature(outcome, include_card, include_astro)
        if groups and groups[-1][0] == signature:
            groups[-1][1].append(rank)
        else:
            groups.append([signature, [rank]])

    messages = []

    for _signature, ranks in groups:
        first = outcomes[ranks[0]]
        lines = []

        # Limits per queue: shown when every rank of the group agrees.
        def limit_key(outcome):
            key = []
            if include_card:
                key.extend(
                    [
                        outcome["rewards"]["CARD"]["per_queue"],
                        outcome["limits"]["FEATHER_S"],
                        outcome["limits"]["FEATHER_A"],
                    ]
                )
            if include_astro:
                key.append(outcome["rewards"]["ASTRO_GC"]["per_queue"])
            return tuple(key)

        keys = {limit_key(outcomes[r]) for r in ranks}
        if len(keys) == 1:
            key = list(next(iter(keys)))
            text = []
            if include_card:
                text.append(f"การ์ด {key[0]} ขาวดำ {key[1]} แดงดำ {key[2]}")
            if include_astro:
                text.append(
                    f"astrocore {key[-1]} {'set' if key[-1] == 1 else 'sets'} (4 ประเภท)"
                )
            lines.append(" ".join(text))
        else:
            lines.append("limit follow rank")

        if include_card:
            lines.append("queue - party")
            width = max(2, len(str(first["queues"])))
            for queue_no in range(1, first["queues"] + 1):
                lines.append(
                    f"{queue_no:0{width}d} - p{party_of(queue_no, queue_start, count)}"
                )

            card_extra = first["rewards"]["CARD"]["extra"]
            if card_extra:
                lines.append("")
                lines.append(f"Extra After Calculate : Card {card_extra}")
                for page, slot, party in first["rewards"]["CARD"]["extra_items"]:
                    lines.append(f"Card Page {page} : Slot {slot} - p{party}")

        if include_astro:
            astro_extra = first["rewards"]["ASTRO_GC"]["extra"]
            if astro_extra:
                lines.append("")
                lines.append(
                    f"Extra After Calculate : Astrocore {astro_extra} "
                    f"{'set' if astro_extra == 1 else 'sets'} (4 ประเภท)"
                )
                lines.extend(
                    _astro_extra_lines(
                        {r: first["rewards"][r]["extra_items"] for r in SPREAD_GROUPS["astro"]}
                    )
                )

        if include_card:
            left = first["feather_left"]
            if left["FEATHER_S"] or left["FEATHER_A"]:
                lines.append("")
                lines.append(
                    f"Extra After Calculate : ขาวดำ {left['FEATHER_S']} "
                    f"แดงดำ {left['FEATHER_A']}"
                )

        title = "Condition Rank " + " ".join(str(r) for r in ranks)
        body = "```\n" + "\n".join(lines) + "\n```"
        if len(body) > 1900:
            blocks = _chunk_blocks(lines[0], lines[1:])
            messages.append(title + "\n" + blocks[0])
            messages.extend(blocks[1:])
        else:
            messages.append(title + "\n" + body)

    if date and messages:
        messages[0] = date + "\n" + messages[0]

    return messages


# -------------------------
# Rank information (/rankinfo): tables and expected results, nothing saved
# -------------------------

RANK_AREAS = {
    "gl": "Guild League / League Prize",
    "Advance": "Emperium Overrun Advance",
    "Normal": "Emperium Overrun Normal",
}


def rank_names(area):
    """Valid rank names for an area (GL/LP ranks are names, Emperium 1-8)."""
    if area == "gl":
        return [name for name, _pool, _limit in RANK_TABLE]
    return [str(n) for n in range(1, len(EMPERIUM_TABLE[area]) + 1)]


def find_rank(area, text):
    """Match what the user typed to a rank name, or None."""
    wanted = text.strip().lower().replace("rank", "").strip()
    for name in rank_names(area):
        if name.lower() == wanted:
            return name
    matches = [name for name in rank_names(area) if wanted and wanted in name.lower()]
    return matches[0] if len(matches) == 1 else None


def _rank_raw(area, rank_name):
    """(pool, limit) tuples of a rank, or None."""
    if area == "gl":
        for name, pool, limit in RANK_TABLE:
            if name == rank_name:
                return pool, limit
        return None
    ranks = EMPERIUM_TABLE.get(area)
    if ranks is None or not rank_name.isdigit() or not 1 <= int(rank_name) <= len(ranks):
        return None
    return ranks[int(rank_name) - 1]


def gl_rank_outcome(rank_name):
    """Expected Guild League / League Prize result of a rank, win case."""
    values = rank_values(rank_name)
    if values is None:
        return None

    def rows(category):
        return [
            {
                "category": category,
                "reward_type": reward,
                "stock": stock,
                "limit_per_queue": limit,
            }
            for reward, (stock, limit) in values.items()
        ]

    ready = {category: rows(category) for category in LINKED}
    counts = {
        category: get_queue_count_from_rewards(category_rows, SPREAD_REWARDS)
        for category, category_rows in ready.items()
    }
    pool = build_extra_pool(ready, counts, SPREAD_REWARDS)
    _stocks, limits = reward_values(next(iter(ready.values())), SPREAD_REWARDS)
    extra_count = count_extra_queues(pool, limits)
    queues = sum(counts.values()) + extra_count
    if queues == 0:
        return None

    spread = compute_spread(ready, queues, 1, 16, {"card": 1, "astro": 1})
    return {
        "per_side": counts[LINKED[0]],
        "extra_queues": extra_count,
        "queues": queues,
        "limits": limits,
        "feather_left": {
            reward: len(pool[reward]) - extra_count * limits[reward]
            for reward in ("FEATHER_S", "FEATHER_A")
        },
        "rewards": spread["rewards"],
    }


def rank_table_lines(area):
    """Every rank of an area: pool and limit per queue."""
    lines = []
    if area == "gl":
        lines.append("GL/LP: Reward (pool ต่อฝั่ง) | limit ต่อคิว")
        rows = [(name, pool, limit) for name, pool, limit in RANK_TABLE]
        width = max(len(name) for name, _p, _l in rows)
    else:
        lines.append(f"Emperium {area}: Reward (pool) | limit ต่อคิว")
        rows = [
            (str(n), pool, limit)
            for n, (pool, limit) in enumerate(EMPERIUM_TABLE[area], 1)
        ]
        width = 4
    lines.append(f"{'Rank':<{width}} Card  LD  TS Astro | limit C/LD/TS/A")
    for name, (card, ld, ts, astro), (lc, lld, lts, la) in rows:
        lines.append(
            f"{name:<{width}} {card:>4} {ld:>3} {ts:>3} {astro:>5} | {lc}/{lld}/{lts}/{la}"
        )
    lines.append("Astro = ต่อชนิด (ชุดละ 4 ประเภท)")
    return lines


def _spread_phrase(item, gl, unit):
    """Words for 'everyone gets N, and the remainder goes ...'."""
    base = item["per_queue"]
    extra = item["extra"] if "extra" in item else item["bonus"] + item["left"]
    if gl:
        tail = f"เศษ +1 ให้ {extra} คิว"
        only = f"+1 ให้ {extra} คิว"
    else:
        tail = f"Extra {extra} {unit}"
        only = f"Extra {extra} {unit}"
    if base and extra:
        return f"ทุกคิวได้ {base}, {tail}"
    if base:
        return f"ทุกคิวได้ {base}"
    return only if extra else "-"


def rank_detail_lines(area, rank_name):
    """Pool, limit and the expected result of one rank."""
    raw = _rank_raw(area, rank_name)
    if raw is None:
        return None
    (card, ld, ts, astro), (lc, lld, lts, la) = raw

    if area == "gl":
        title = f"{rank_name} (GL/LP กรณีชนะ)"
        outcome = gl_rank_outcome(rank_name)
    else:
        title = f"Emperium {area} rank {rank_name}"
        outcome = emperium_outcome(
            _emperium_rows(emperium_rank_values(area, int(rank_name))), 1, 16,
            {"card": 1, "astro": 1},
        )
    if outcome is None:
        return None

    pool_label = "Pool ต่อฝั่ง" if area == "gl" else "Pool"
    lines = [
        title,
        f"{pool_label}: Card {card} | ขาวดำ {ld} | แดงดำ {ts} | Astrocore {astro} (ต่อชนิด)",
        f"Limit ต่อคิว: Card {lc} | ขาวดำ {lld} | แดงดำ {lts} | Astrocore {la} (ต่อชนิด)",
    ]

    if area == "gl":
        total = outcome["queues"]
        detail = f"GL {outcome['per_side']} + LP {outcome['per_side']}"
        if outcome["extra_queues"]:
            detail += f" + Extra {outcome['extra_queues']}"
        lines.append(f"ผล: {total} คิว ({detail})")
        unit_card = f"รวม 2 ฝั่ง {card * 2} ใบ"
        unit_astro = f"รวม 2 ฝั่ง {astro * 2} ชุด"
    else:
        lines.append(f"ผล: {outcome['queues']} คิว")
        unit_card = f"pool {card} ใบ"
        unit_astro = f"pool {astro} ชุด"

    limits = outcome["limits"]
    lines.append(
        f"ขาวดำ/แดงดำ: ทุกคิวได้ {limits['FEATHER_S']} / {limits['FEATHER_A']}"
    )
    rewards = outcome["rewards"]
    gl = area == "gl"
    lines.append(f"Card ({unit_card}): {_spread_phrase(rewards['CARD'], gl, 'ใบ')}")
    lines.append(
        f"Astrocore ({unit_astro}, 1 ชุด = 4 ประเภท): "
        f"{_spread_phrase(rewards['ASTRO_GC'], gl, 'ชุด')}"
    )

    left = outcome["feather_left"]
    if left["FEATHER_S"] or left["FEATHER_A"]:
        lines.append(f"ขนนกเหลือ (Extra ไม่แจก): ขาวดำ {left['FEATHER_S']} / แดงดำ {left['FEATHER_A']}")
    else:
        lines.append("ขนนกเหลือ: ไม่มี")

    if area == "gl":
        lines.append("แพ้ => ของ League Prize ลดลง ผลจะต่างจากนี้")
    else:
        lines.append("Extra แจกให้ปาร์ตี้ใบ/ชุดละ 1 ตามลำดับปาร์ตี้")
    return lines
