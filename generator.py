from database import (
    clear_queue,
    save_queue_position,
    get_rewards,
)

ITEM_PER_PAGE = 4
REWARD_ORDER = ("CARD", "FEATHER_S", "FEATHER_A")


def position_from_index(index):
    return index // ITEM_PER_PAGE + 1, index % ITEM_PER_PAGE + 1


def _ensure_reward_map(rows):
    # convert DB rows to dict with defaults
    reward_map = {}
    for r in rows:
        reward_map[r["reward_type"]] = {
            "stock": r["stock"],
            "limit_per_queue": r["limit_per_queue"],
        }
    # ensure keys exist
    for key in REWARD_ORDER:
        reward_map.setdefault(key, {"stock": 0, "limit_per_queue": 0})
    return reward_map


def generate_queues(guild_id: str, category: str | None = "Guild League") -> dict:
    """
    Generate queues for the given category.
    - If category is "Guild League" or "League Prize", both categories are generated together using the GL-first algorithm.
    - If category is None or "All", generate for all categories (GL+LP linked, others independently).

    Returns a dict mapping category name -> number of queues generated.
    """

    results = {}

    # Helper to generate for a single independent category
    def _generate_single(cat_name):
        clear_queue(guild_id, cat_name)
        rows = get_rewards(guild_id, cat_name)
        reward_map = _ensure_reward_map(rows)

        # validate limits
        limits = [reward_map[r]["limit_per_queue"] for r in REWARD_ORDER]
        if any(l < 1 for l in limits):
            return 0

        # compute how many full queues this category can provide
        counts = [reward_map[r]["stock"] // reward_map[r]["limit_per_queue"] for r in REWARD_ORDER]
        queue_count = min(counts)

        # per-reward index for page/slot numbering (per category)
        # FEATHER_A slots should start after all FEATHER_S slots (S then A)
        indices = {
            "CARD": 0,
            "FEATHER_S": 0,
            "FEATHER_A": reward_map["FEATHER_S"]["stock"]  # a_index starts after total S stock
        }

        for q in range(1, queue_count + 1):
            for r in REWARD_ORDER:
                for _ in range(reward_map[r]["limit_per_queue"]):
                    page, slot = position_from_index(indices[r])
                    save_queue_position(guild_id, q, r, page, slot, cat_name)
                    indices[r] += 1
                    reward_map[r]["stock"] -= 1
        return queue_count

    # Linked GL + LP generator
    def _generate_gl_lp(gl_name="Guild League", lp_name="League Prize"):
        # clear both categories
        clear_queue(guild_id, gl_name)
        clear_queue(guild_id, lp_name)

        gl_rows = get_rewards(guild_id, gl_name)
        lp_rows = get_rewards(guild_id, lp_name)

        gl_map = _ensure_reward_map(gl_rows)
        lp_map = _ensure_reward_map(lp_rows)

        # validate limits (we expect limits to be set and synced, but guard anyway)
        limits = [gl_map[r]["limit_per_queue"] for r in REWARD_ORDER]
        if any(l < 1 for l in limits):
            return {gl_name: 0, lp_name: 0}

        # Phase 1: produce full queues from GL alone
        gl_counts = [gl_map[r]["stock"] // gl_map[r]["limit_per_queue"] for r in REWARD_ORDER]
        gl_full = min(gl_counts)

        # per-reward indices
        gl_indices = {
            "CARD": 0,
            "FEATHER_S": 0,
            # FEATHER_A starts after all FEATHER_S positions for GL
            "FEATHER_A": gl_map["FEATHER_S"]["stock"]
        }
        lp_indices = {
            "CARD": 0,
            "FEATHER_S": 0,
            # FEATHER_A starts after all FEATHER_S positions for LP
            "FEATHER_A": lp_map["FEATHER_S"]["stock"]
        }

        qno = 0
        for _ in range(gl_full):
            qno += 1
            for r in REWARD_ORDER:
                for _ in range(gl_map[r]["limit_per_queue"]):
                    page, slot = position_from_index(gl_indices[r])
                    save_queue_position(guild_id, qno, r, page, slot, gl_name)
                    gl_indices[r] += 1
                    gl_map[r]["stock"] -= 1

        # Phase 2: produce full queues from LP alone
        lp_counts = [lp_map[r]["stock"] // lp_map[r]["limit_per_queue"] for r in REWARD_ORDER]
        lp_full = min(lp_counts)
        for _ in range(lp_full):
            qno += 1
            for r in REWARD_ORDER:
                for _ in range(lp_map[r]["limit_per_queue"]):
                    page, slot = position_from_index(lp_indices[r])
                    save_queue_position(guild_id, qno, r, page, slot, lp_name)
                    lp_indices[r] += 1
                    lp_map[r]["stock"] -= 1

        # Phase 3: attempt one final combined queue using GL then LP leftovers
        can_combined = all((gl_map[r]["stock"] + lp_map[r]["stock"]) >= gl_map[r]["limit_per_queue"] for r in REWARD_ORDER)
        combined_created = 0
        if can_combined:
            qno += 1
            for r in REWARD_ORDER:
                need = gl_map[r]["limit_per_queue"]
                # take from GL first
                take_gl = min(gl_map[r]["stock"], need)
                for _ in range(take_gl):
                    page, slot = position_from_index(gl_indices[r])
                    save_queue_position(guild_id, qno, r, page, slot, gl_name)
                    gl_indices[r] += 1
                    gl_map[r]["stock"] -= 1
                    need -= 1
                # then from LP
                take_lp = min(lp_map[r]["stock"], need)
                for _ in range(take_lp):
                    page, slot = position_from_index(lp_indices[r])
                    save_queue_position(guild_id, qno, r, page, slot, lp_name)
                    lp_indices[r] += 1
                    lp_map[r]["stock"] -= 1
                    need -= 1
            combined_created = 1

        return {gl_name: gl_full + combined_created, lp_name: lp_full + combined_created}

    # Main dispatch
    if category is None or category == "All":
        # GL+LP linked
        gl_lp_counts = _generate_gl_lp()
        results.update(gl_lp_counts)
        # generate others independently
        for cat in ("Emperium Overrun", "Designed Auction"):
            count = _generate_single(cat)
            results[cat] = count
    elif category in ("Guild League", "League Prize"):
        # generate both linked; return counts for both
        results.update(_generate_gl_lp())
    else:
        # single independent category
        results[category] = _generate_single(category)

    return results
