from database import (
    init_database,
    set_reward_limit,
    set_reward_stock,
    get_all_queue,
    get_rewards,
    get_assigned_count,
)
from generator import generate_queues


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
            print(f"- {reward}: Stock={row['stock']} In queues={assigned} Extra={extra}")


if __name__ == '__main__':
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

    result = generate_queues(GUILD, 'All')
    print('\n/generate (response)')
    print('✅ Queue Generated')
    print('\nTotal queues per category:')
    for k, v in result.items():
        print(f'- {k}: {v}')

    # print sample queues 1,10,11,15 if they exist
    print_queues(GUILD)
    print_extra(GUILD)
