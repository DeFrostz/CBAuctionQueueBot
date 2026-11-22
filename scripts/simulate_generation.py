"""
Simulate /generate without Discord.

Run from the repo root:  python -m scripts.simulate_generation
Uses a temporary database, so data/auction.db is never touched.
"""
import tempfile
from pathlib import Path

import database
from constants import CATEGORIES, position
from database import (
    init_database,
    set_reward_limit,
    set_reward_stock,
    get_all_queue,
    get_rewards,
    get_assigned_count,
)
from generator import check_categories, generate_all


def print_queues(guild_id):
    rows = get_all_queue(guild_id)
    if not rows:
        print("No queues generated")
        return

    queues = {}
    for r in rows:
        queues.setdefault(r['queue_no'], {}).setdefault((r['category'], r['reward_type']), []).append(r)

    for qno in sorted(queues.keys()):
        print(f"\n📋 Queue #{qno}")
        grouped_by_cat = {}
        for (cat, reward), items in queues[qno].items():
            grouped_by_cat.setdefault(cat, {}).setdefault(reward, []).extend(items)

        for cat in grouped_by_cat:
            print(f"\nCategory: {cat}")
            for reward in ("CARD", "FEATHER_S", "FEATHER_A"):
                rows = grouped_by_cat[cat].get(reward)
                if not rows:
                    continue
                print({
                    'CARD': '🃏 Card',
                    'FEATHER_S': '🌗 Light-Dark',
                    'FEATHER_A': '⏳ Time-Space'
                }[reward])
                # group slots
                pages = {}
                for r in rows:
                    pages.setdefault(r['page'], []).append(r['slot'])
                for page in sorted(pages.keys()):
                    slots = sorted(pages[page])
                    if len(slots) == 1:
                        slot_text = str(slots[0])
                    else:
                        slot_text = f"{slots[0]}-{slots[-1]}"
                    print(f"- Page {page} : Slot {slot_text}")


def print_extra(guild_id):
    print("\n/extra category=All")
    for cat in ("Guild League", "League Prize", "Emperium Overrun", "Designed Auction"):
        print(f"\nCategory: {cat}")
        rewards = {r['reward_type']: r for r in get_rewards(guild_id, cat)}
        for reward in ("CARD", "FEATHER_S", "FEATHER_A"):
            row = rewards.get(reward)
            if not row:
                print(f"- {reward}: Not configured")
                continue
            assigned = get_assigned_count(guild_id, cat, reward)
            extra = max(row['stock'] - assigned, 0)
            # Time-Space positions start after all Light-Dark stock (same as /extra).
            start = assigned
            if reward == 'FEATHER_A' and 'FEATHER_S' in rewards:
                start += rewards['FEATHER_S']['stock']
            positions = []
            for index in range(start, start + extra):
                page, slot = position(index)
                positions.append(f"Page {page} : Slot {slot}")
            if positions:
                print(f"- {reward}: Stock={row['stock']} In queues={assigned} Extra={extra} Positions:")
                for p in positions:
                    print(f"  - {p}")
            else:
                print(f"- {reward}: Stock={row['stock']} In queues={assigned} Extra={extra} Positions: None")


if __name__ == '__main__':
    database.DB_PATH = Path(tempfile.mkdtemp()) / 'simulate.db'
    init_database()
    GUILD = 'SIM_GUILD'

    # Limits per category (set on Guild League, will be applied to League Prize too by admin logic normally)
    set_reward_limit(GUILD, 'CARD', 2, 'Guild League')
    set_reward_limit(GUILD, 'FEATHER_S', 8, 'Guild League')
    set_reward_limit(GUILD, 'FEATHER_A', 10, 'Guild League')
    # apply same limits to League Prize to emulate admin linked behavior
    set_reward_limit(GUILD, 'CARD', 2, 'League Prize')
    set_reward_limit(GUILD, 'FEATHER_S', 8, 'League Prize')
    set_reward_limit(GUILD, 'FEATHER_A', 10, 'League Prize')

    # Stocks
    set_reward_stock(GUILD, 'CARD', 20, 'Guild League')
    set_reward_stock(GUILD, 'FEATHER_S', 84, 'Guild League')
    set_reward_stock(GUILD, 'FEATHER_A', 105, 'Guild League')

    set_reward_stock(GUILD, 'CARD', 10, 'League Prize')
    set_reward_stock(GUILD, 'FEATHER_S', 42, 'League Prize')
    set_reward_stock(GUILD, 'FEATHER_A', 52, 'League Prize')

    category_rewards, skipped = check_categories(GUILD, list(CATEGORIES))
    summary = generate_all(GUILD, category_rewards)
    print('\n/generate (response)')
    print('✅ Queue Generated')
    print('\nQueues per category:')
    for k, v in summary['results'].items():
        print(f"- {k}: {v['count']} (Queue {v['start']}-{v['end']})")
    if summary['extra_count']:
        print(f"- GL/LP Extra: {summary['extra_count']} (Queue {summary['extra_start']}-{summary['extra_end']})")
    print(f"Remaining GL/LP Extra: {summary['remaining_extra']}")
    for cat, reason in skipped:
        print(f'Skipped {cat}: {reason}')

    # print sample queues 1,10,11,15 if they exist
    print_queues(GUILD)
    print_extra(GUILD)
