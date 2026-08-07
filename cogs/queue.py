import discord

from discord.ext import commands

from database import (
    get_all_queue,
    get_queue,
    get_rewards,
    get_assigned_count,
    CATEGORIES,
)


# Guild League + League Prize ใช้ระบบ Queue ร่วมกัน
LINKED = (
    "Guild League",
    "League Prize",
)


REWARD_ORDER = (
    "CARD",
    "FEATHER_S",
    "FEATHER_A",
)


REWARD_NAMES = {
    "CARD": "🃏 Card",
    "FEATHER_S": "🌗 Light-Dark",
    "FEATHER_A": "⏳ Time-Space",
}


class Queue(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # =========================================================
    # Helpers
    # =========================================================

    def group_slots(self, rows):
        """
        รวม Slot ที่อยู่ Page เดียวกัน

        ตัวอย่าง:

        Page 1 Slot 1
        Page 1 Slot 2
        Page 1 Slot 3

        =>

        Page 1 : Slot 1-3
        """

        pages = {}

        for row in rows:
            page = row["page"]
            slot = row["slot"]

            pages.setdefault(page, []).append(slot)

        result = []

        for page in sorted(pages):
            slots = sorted(pages[page])

            if len(slots) == 1:
                slot_text = str(slots[0])

            else:
                slot_text = f"{slots[0]}-{slots[-1]}"

            result.append(f"Page {page} : Slot {slot_text}")

        return "\n".join(result)

    def group_position_range(
        self,
        start_index,
        amount,
    ):
        """
        Convert absolute index -> Page / Slot

        4 items per page
        """

        if amount <= 0:
            return "None"

        pages = {}

        for index in range(
            start_index,
            start_index + amount,
        ):
            page = index // 4 + 1
            slot = index % 4 + 1

            pages.setdefault(page, []).append(slot)

        result = []

        for page in sorted(pages):
            slots = sorted(pages[page])

            if len(slots) == 1:
                slot_text = str(slots[0])

            else:
                slot_text = f"{slots[0]}-{slots[-1]}"

            result.append(f"Page {page} : Slot {slot_text}")

        return "\n".join(result)

    def get_selected_categories(
        self,
        category,
    ):
        """
        Category filter behavior:

        None
            -> ทุก Category

        Guild League
            -> Guild League + League Prize

        League Prize
            -> Guild League + League Prize

        Emperium Overrun
            -> Emperium Overrun only

        Designed Auction
            -> Designed Auction only
        """

        if category is None or category.value == "All":
            return None

        category_value = category.value

        if category_value in LINKED:
            return LINKED

        return (category_value,)

    # =========================================================
    # /extra
    # =========================================================

    @discord.app_commands.command(
        name="extra",
        description=("View rewards that are not assigned to a queue"),
    )
    async def extra(
        self,
        interaction: discord.Interaction,
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used in a server"
            )

            return

        guild_id = str(interaction.guild.id)

        embed = discord.Embed(
            title="📦 Extra Rewards",
            description=("Rewards not assigned to queues"),
        )

        for category in CATEGORIES:
            reward_rows = get_rewards(
                guild_id,
                category,
            )

            rewards = {row["reward_type"]: row for row in reward_rows}

            # ไม่มี config เลย
            if not rewards:
                embed.add_field(
                    name=f"📂 {category}",
                    value="Not configured",
                    inline=False,
                )

                continue

            # สำคัญ:
            # อย่าใช้ get_queue_count()
            # เพราะ Queue ของ LP อาจเป็น 11-15
            #
            # MAX(queue_no) = 15
            # แต่จริง ๆ มีแค่ 5 queues
            queue_rows = get_all_queue(
                guild_id,
                category,
            )

            queue_numbers = {row["queue_no"] for row in queue_rows}

            queue_count = len(queue_numbers)

            category_lines = [f"**Queues: {queue_count}**"]

            for reward in REWARD_ORDER:
                row = rewards.get(reward)

                if row is None:
                    category_lines.append(f"{REWARD_NAMES[reward]}\nNot configured")

                    continue

                stock = int(row["stock"])

                # ใช้จำนวน position จริง
                # ที่อยู่ใน queue_plan
                assigned = get_assigned_count(
                    guild_id,
                    category,
                    reward,
                )

                extra = max(
                    stock - assigned,
                    0,
                )

                if extra == 0:
                    positions = "None"

                else:
                    # ของที่ถูก assign จะใช้
                    # จากหน้าแรกไปเรื่อย ๆ
                    start_index = assigned

                    # Feather A ต่อจาก Feather S
                    # ใน Filter เดียวกัน
                    if reward == "FEATHER_A":
                        feather_s = rewards.get("FEATHER_S")

                        feather_s_stock = int(feather_s["stock"]) if feather_s else 0

                        start_index = feather_s_stock + assigned

                    positions = self.group_position_range(
                        start_index,
                        extra,
                    )

                category_lines.append(
                    f"{REWARD_NAMES[reward]}\n"
                    f"Stock: {stock}\n"
                    f"In queues: {assigned}\n"
                    f"Extra: **{extra}**\n"
                    f"Positions:\n"
                    f"{positions}"
                )

            embed.add_field(
                name=f"📂 {category}",
                value="\n\n".join(category_lines),
                inline=False,
            )

        await interaction.response.send_message(embed=embed)

    # =========================================================
    # /queuelist
    # =========================================================

    @discord.app_commands.command(
        name="queuelist",
        description=("View queues by number and/or category"),
    )
    @discord.app_commands.choices(
        category=[
            discord.app_commands.Choice(
                name=cat,
                value=cat
            )
            for cat in (*CATEGORIES, "All")
        ]
    )
    @discord.app_commands.describe(
        number="Optional queue number",
        category="Optional category (All by default)",
    )
    async def queue(
        self,
        interaction: discord.Interaction,
        number: int | None = None,
        category: (discord.app_commands.Choice[str] | None) = None,
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used in a server"
            )

            return

        guild_id = str(interaction.guild.id)

        # -----------------------------------------
        # Category selection
        # -----------------------------------------

        selected_categories = self.get_selected_categories(category)

        # -----------------------------------------
        # Load Queue Data
        # -----------------------------------------

        if number is not None:
            # No category filter
            if selected_categories is None:
                data = get_queue(
                    guild_id,
                    number,
                )

            # Category filter
            else:
                data = []

                for cat in selected_categories:
                    rows = get_queue(
                        guild_id,
                        number,
                        cat,
                    )

                    data.extend(rows)

        else:
            # No category filter
            if selected_categories is None:
                data = get_all_queue(guild_id)

            # Category filter
            else:
                data = []

                for cat in selected_categories:
                    rows = get_all_queue(
                        guild_id,
                        cat,
                    )

                    data.extend(rows)

        # -----------------------------------------
        # Nothing found
        # -----------------------------------------

        if not data:
            category_name = category.value if category is not None else None

            if number is not None and category_name is not None:
                message = f"❌ Queue #{number} not found in **{category_name}**"

            elif number is not None:
                message = f"❌ Queue #{number} not found"

            elif category_name is not None:
                message = f"❌ No queues found for **{category_name}**"

            else:
                message = "❌ No queues generated yet. Use `/generate` first."

            await interaction.response.send_message(message)

            return

        # -----------------------------------------
        # Group
        #
        # queue_no
        #   └ category
        #       └ reward
        # -----------------------------------------

        queues = {}

        for row in data:
            queue_no = row["queue_no"]

            row_category = row["category"]

            reward_type = row["reward_type"]

            (
                queues.setdefault(
                    queue_no,
                    {},
                )
                .setdefault(
                    row_category,
                    {},
                )
                .setdefault(
                    reward_type,
                    [],
                )
                .append(row)
            )

        # -----------------------------------------
        # Build output
        # -----------------------------------------

        sections = []

        for queue_no in sorted(queues):
            category_groups = queues[queue_no]

            lines = [f"📋 Queue #{queue_no}"]

            # Keep normal category order
            for cat in CATEGORIES:
                reward_groups = category_groups.get(cat)

                if not reward_groups:
                    continue

                lines.append(f"\n**{cat}**")

                for reward in REWARD_ORDER:
                    rows = reward_groups.get(reward)

                    if not rows:
                        continue

                    lines.append(
                        REWARD_NAMES.get(
                            reward,
                            reward,
                        )
                    )

                    positions = self.group_slots(rows)

                    lines.extend(f"- {position}" for position in positions.splitlines())

            sections.append("\n".join(lines))

        # -----------------------------------------
        # Discord has message size limit.
        # Split around 1900 chars.
        # -----------------------------------------

        chunks = []

        current = ""

        for section in sections:
            candidate = (f"{current}\n\n{section}").strip()

            if current and len(candidate) > 1900:
                chunks.append(current)

                current = section

            else:
                current = candidate

        if current:
            chunks.append(current)

        # -----------------------------------------
        # Send
        # -----------------------------------------

        await interaction.response.send_message(chunks[0])

        for chunk in chunks[1:]:
            await interaction.followup.send(chunk)


async def setup(bot):
    await bot.add_cog(Queue(bot))
