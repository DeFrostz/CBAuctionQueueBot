from database import (
    clear_queue,
    save_queue_position
)



ITEM_PER_PAGE = 4



def position(index):

    return (
        index // ITEM_PER_PAGE + 1,
        index % ITEM_PER_PAGE + 1
    )



def generate_queue(
    guild_id,
    rewards
):

    clear_queue(guild_id)


    reward_map = {}

    for r in rewards:

        reward_map[
            r["reward_type"]
        ] = r



    card = reward_map.get(
        "CARD"
    )

    feather_s = reward_map.get(
        "FEATHER_S"
    )

    feather_a = reward_map.get(
        "FEATHER_A"
    )



    # จำนวน Queue สูงสุด
    queue_count = min(

        card["stock"]
        // card["limit_per_queue"],


        feather_s["stock"]
        // feather_s["limit_per_queue"],


        feather_a["stock"]
        // feather_a["limit_per_queue"]

    )



    card_index = 0

    s_index = 0

    # A ต่อจาก S
    a_index = feather_s["stock"]



    for queue in range(
        1,
        queue_count + 1
    ):


        # CARD

        for _ in range(
            card["limit_per_queue"]
        ):

            page,slot = position(
                card_index
            )

            save_queue_position(
                guild_id,
                queue,
                "CARD",
                page,
                slot
            )

            card_index += 1



        # FEATHER S

        for _ in range(
            feather_s["limit_per_queue"]
        ):

            page,slot = position(
                s_index
            )


            save_queue_position(
                guild_id,
                queue,
                "FEATHER_S",
                page,
                slot
            )


            s_index += 1




        # FEATHER A

        for _ in range(
            feather_a["limit_per_queue"]
        ):

            page,slot = position(
                a_index
            )


            save_queue_position(
                guild_id,
                queue,
                "FEATHER_A",
                page,
                slot
            )


            a_index += 1



    return queue_count