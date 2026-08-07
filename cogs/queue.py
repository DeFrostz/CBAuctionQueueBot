import discord

from discord.ext import commands

from database import (
    get_all_queue,
    get_queue,
    get_rewards,
    get_assigned_count,
    CATEGORIES,
)


# Guild League + League Prize share the same queue sequence
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
        Group slots that are on the same page.

        Example:

        Page 1 Slot 1
        Page 1 Slot 2
        Page 1 Slot 3

        ->

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
        Convert absolute item indexes to Page / Slot.

        4 items per page.
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
        /queuelist category behavior

        None / All
            -> all categories

        Guild League
            -> Guild League + League Prize

        League Prize
            -> Guild League + League Prize

        Emperium Overrun
            -> Emperium only

        Designed Auction
            -> Designed only
        """

        if category is None or category.value == "All":
            return None

        category_value = category.value

        if category_value in LINKED:
            return LINKED

        return (category_value,)

    def build_queue_value(
        self,
        reward_groups,
    ):
        """
        Build one queue's reward display.
        """

        value_lines = []

        for reward in REWARD_ORDER:
            rows = reward_groups.get(reward)

            if not rows:
                continue

            value_lines.append(
                REWARD_NAMES.get(
                    reward,
                    reward,
                )
            )

            positions = self.group_slots(rows)

            value_lines.extend(positions.splitlines())

            value_lines.append("")

        return "\n".join(value_lines).strip()

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
            description="Rewards not assigned to queues",
        )

        for category_name in CATEGORIES:
            reward_rows = get_rewards(
                guild_id,
                category_name,
            )

            rewards = {row["reward_type"]: row for row in reward_rows}

            # Category has never been configured
            if not rewards:
                embed.add_field(
                    name=f"📂 {category_name}",
                    value="Not configured",
                    inline=False,
                )

                continue

            # Count real queue numbers for this category.
            #
            # Do not use MAX(queue_no), because League Prize
            # may contain Queue 11-15 but that is only 5 queues.
            queue_rows = get_all_queue(
                guild_id,
                category_name,
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

                # Number of actual positions assigned
                # to queues for this category/reward.
                assigned = get_assigned_count(
                    guild_id,
                    category_name,
                    reward,
                )

                extra = max(
                    stock - assigned,
                    0,
                )

                if extra == 0:
                    positions = "None"

                else:
                    start_index = assigned

                    # Feather A continues after all Feather S
                    # in the same filter.
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
                name=f"📂 {category_name}",
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
                value=cat,
            )
            for cat in (*CATEGORIES, "All")
        ]
    )
    @discord.app_commands.describe(
        number="Optional queue number",
        category="Optional category (All by default)",
    )
    async def queuelist(
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

        # =====================================================
        # Category selection
        # =====================================================

        selected_categories = self.get_selected_categories(category)

        # =====================================================
        # Load data
        # =====================================================

        if number is not None:
            # All categories
            if selected_categories is None:
                data = get_queue(
                    guild_id,
                    number,
                )

            # Filtered categories
            else:
                data = []

                for category_name in selected_categories:
                    rows = get_queue(
                        guild_id,
                        number,
                        category_name,
                    )

                    data.extend(rows)

        else:
            # All categories
            if selected_categories is None:
                data = get_all_queue(guild_id)

            # Filtered categories
            else:
                data = []

                for category_name in selected_categories:
                    rows = get_all_queue(
                        guild_id,
                        category_name,
                    )

                    data.extend(rows)

        # =====================================================
        # Nothing found
        # =====================================================

        if not data:
            category_name = category.value if category is not None else None

            if number is not None and category_name is not None:
                message = f"❌ Queue #{number} not found in **{category_name}**"

            elif number is not None:
                message = f"❌ Queue #{number} not found"

            elif category_name is not None and category_name != "All":
                message = f"❌ No queues found for **{category_name}**"

            else:
                message = "❌ No queues generated yet. Use `/generate` first."

            await interaction.response.send_message(message)

            return

        # =====================================================
        # Group queue data
        #
        # GL + LP:
        #
        # ("LINKED", queue_no)
        #
        # Independent:
        #
        # ("Emperium Overrun", queue_no)
        # ("Designed Auction", queue_no)
        # =====================================================

        queues = {}

        for row in data:
            queue_no = row["queue_no"]

            row_category = row["category"]

            reward_type = row["reward_type"]

            # GL + LP share queue numbering
            if row_category in LINKED:
                group_key = (
                    "LINKED",
                    queue_no,
                )

            # Independent categories
            else:
                group_key = (
                    row_category,
                    queue_no,
                )

            (
                queues.setdefault(
                    group_key,
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

        # =====================================================
        # Build embeds
        # =====================================================

        embeds = []

        # Discord limits:
        # - max 25 fields per embed
        # - max ~6000 chars total per embed
        MAX_FIELDS = 20
        MAX_EMBED_CHARS = 5500
        MAX_FIELD_VALUE = 1024

        def create_embed(
            title,
            continued=False,
        ):
            if continued:
                title = f"{title} • Continued"

            return discord.Embed(
                title=title,
                description="Auction Queue List",
            )

        def embed_size(embed):
            size = len(embed.title or "") + len(embed.description or "")

            for field in embed.fields:
                size += len(field.name)

                size += len(field.value)

            return size

        def split_value(
            value,
            max_length=MAX_FIELD_VALUE,
        ):
            """
            Split a field value safely without
            breaking Discord's 1024 char field limit.
            """

            if len(value) <= max_length:
                return [value]

            parts = []
            current = ""

            for line in value.splitlines():
                candidate = f"{current}\n{line}" if current else line

                if len(candidate) > max_length:
                    if current:
                        parts.append(current)

                    current = line

                else:
                    current = candidate

            if current:
                parts.append(current)

            return parts

        def add_queue_to_embeds(
            embed_list,
            current_embed,
            embed_title,
            queue_no,
            value,
        ):
            """
            Add Queue field safely.

            Starts another embed when:
            - field count is getting too high
            - embed is getting too large
            """
            separator = "────────────────────"

            queue_value = (
                f"{value}\n\n{separator}"
                if value
                else separator
            )
            
            values = split_value(
                queue_value
            )

            for index, field_value in enumerate(values):
                if index == 0:
                    field_name = f"📋 Queue #{queue_no}"

                else:
                    field_name = f"↳ Queue #{queue_no} (continued)"

                estimated_size = (
                    embed_size(current_embed) + len(field_name) + len(field_value)
                )

                if (
                    len(current_embed.fields) >= MAX_FIELDS
                    or estimated_size >= MAX_EMBED_CHARS
                ):
                    if current_embed.fields:
                        embed_list.append(current_embed)

                    current_embed = create_embed(
                        embed_title,
                        continued=True,
                    )

                current_embed.add_field(
                    name=field_name,
                    value=field_value,
                    inline=False,
                )

            return current_embed

        # =====================================================
        # Guild League + League Prize
        # =====================================================

        linked_keys = [key for key in queues if key[0] == "LINKED"]

        if linked_keys:
            embed_title = "🏆 Guild League / League Prize"

            embed = create_embed(embed_title)

            for _, queue_no in sorted(
                linked_keys,
                key=lambda x: x[1],
            ):
                category_groups = queues[("LINKED", queue_no)]

                value_lines = []

                for linked_category in LINKED:
                    reward_groups = category_groups.get(linked_category)

                    if not reward_groups:
                        continue

                    # Show category inside linked queue
                    # because an Extra Queue may contain
                    # items from both GL and LP.
                    value_lines.append(f"**{linked_category}**")

                    queue_value = self.build_queue_value(reward_groups)

                    if queue_value:
                        value_lines.append(queue_value)

                    value_lines.append("")

                value = "\n".join(value_lines).strip()

                embed = add_queue_to_embeds(
                    embeds,
                    embed,
                    embed_title,
                    queue_no,
                    value,
                )

            if embed.fields:
                embeds.append(embed)

        # =====================================================
        # Independent categories
        # =====================================================

        for independent_category in (
            "Emperium Overrun",
            "Designed Auction",
        ):
            category_keys = [key for key in queues if key[0] == independent_category]

            if not category_keys:
                continue

            embed_title = f"📂 {independent_category}"

            embed = create_embed(embed_title)

            for _, queue_no in sorted(
                category_keys,
                key=lambda x: x[1],
            ):
                category_groups = queues[
                    (
                        independent_category,
                        queue_no,
                    )
                ]

                reward_groups = category_groups.get(independent_category)

                if not reward_groups:
                    continue

                value = self.build_queue_value(reward_groups)

                embed = add_queue_to_embeds(
                    embeds,
                    embed,
                    embed_title,
                    queue_no,
                    value,
                )

            if embed.fields:
                embeds.append(embed)

        # =====================================================
        # Send
        # =====================================================

        if not embeds:
            await interaction.response.send_message("❌ No queue data found.")

            return

        # First response
        await interaction.response.send_message(embed=embeds[0])

        # Additional embeds
        for embed in embeds[1:]:
            await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Queue(bot))
