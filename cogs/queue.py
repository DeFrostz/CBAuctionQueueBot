import discord

from discord.ext import commands

from database import (
    get_all_queue,
    get_queue,
    get_rewards,
    get_assigned_count,
    CATEGORIES,
)


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

    def group_slots(self, rows):
        pages = {}
        for row in rows:
            pages.setdefault(row["page"], []).append(row["slot"])

        result = []
        for page in sorted(pages):
            slots = sorted(pages[page])
            slot_text = str(slots[0]) if len(slots) == 1 else f"{slots[0]}-{slots[-1]}"
            result.append(f"Page {page} : Slot {slot_text}")
        return "\n".join(result)

    def group_position_range(self, start_index, amount):
        if amount <= 0:
            return "None"

        pages = {}
        for index in range(start_index, start_index + amount):
            page = index // 4 + 1
            slot = index % 4 + 1
            pages.setdefault(page, []).append(slot)

        result = []
        for page in sorted(pages):
            slots = sorted(pages[page])
            slot_text = str(slots[0]) if len(slots) == 1 else f"{slots[0]}-{slots[-1]}"
            result.append(f"Page {page} : Slot {slot_text}")
        return "\n".join(result)

    def get_selected_categories(self, category):
        if category is None or category.value == "All":
            return None
        if category.value in LINKED:
            return LINKED
        return (category.value,)

    def build_queue_value(self, reward_groups):
        value_lines = []
        for reward in REWARD_ORDER:
            rows = reward_groups.get(reward)
            if not rows:
                continue
            value_lines.append(REWARD_NAMES.get(reward, reward))
            value_lines.extend(self.group_slots(rows).splitlines())
            value_lines.append("")
        return "\n".join(value_lines).strip()

    @discord.app_commands.command(
        name="extra",
        description="View remaining rewards that are not assigned to a queue",
    )
    @discord.app_commands.choices(
        category=[
            discord.app_commands.Choice(name=cat, value=cat)
            for cat in (*CATEGORIES, "All")
        ]
    )
    @discord.app_commands.describe(category="Optional category (All by default)")
    async def extra(
        self,
        interaction: discord.Interaction,
        category: discord.app_commands.Choice[str] | None = None,
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used in a server",
                ephemeral=True,
            )
            return

        guild_id = str(interaction.guild.id)

        if category is None or category.value == "All":
            selected_categories = list(CATEGORIES)
        elif category.value in LINKED:
            selected_categories = list(LINKED)
        else:
            selected_categories = [category.value]

        embed = discord.Embed(
            title="📦 Remaining Rewards",
            description="Rewards not assigned to queues",
        )

        has_remaining = False

        for category_name in selected_categories:
            reward_rows = get_rewards(guild_id, category_name)
            rewards = {row["reward_type"]: row for row in reward_rows}

            if not rewards:
                continue

            category_lines = []

            for reward in REWARD_ORDER:
                row = rewards.get(reward)
                if row is None:
                    continue

                stock = int(row["stock"])
                assigned = get_assigned_count(
                    guild_id,
                    category_name,
                    reward,
                )
                remaining = max(stock - assigned, 0)

                # /extra is a remaining-items view, so hide empty rewards.
                if remaining <= 0:
                    continue

                start_index = assigned

                # Feather A positions continue after all Feather S stock.
                if reward == "FEATHER_A":
                    feather_s = rewards.get("FEATHER_S")
                    feather_s_stock = int(feather_s["stock"]) if feather_s else 0
                    start_index = feather_s_stock + assigned

                positions = self.group_position_range(
                    start_index,
                    remaining,
                )

                category_lines.append(
                    f"{REWARD_NAMES[reward]}\n"
                    f"Remaining: **{remaining}**\n"
                    f"Positions:\n{positions}"
                )

            # Hide categories where every reward has zero remaining.
            if not category_lines:
                continue

            has_remaining = True
            embed.add_field(
                name=f"📂 {category_name}",
                value="\n\n".join(category_lines),
                inline=False,
            )

        if not has_remaining:
            await interaction.response.send_message(
                "✅ No remaining rewards.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(embed=embed)

    @discord.app_commands.command(
        name="queuelist",
        description="View queues by number and/or category",
    )
    @discord.app_commands.choices(
        category=[
            discord.app_commands.Choice(name=cat, value=cat)
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
        category: discord.app_commands.Choice[str] | None = None,
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used in a server"
            )
            return

        guild_id = str(interaction.guild.id)
        selected_categories = self.get_selected_categories(category)

        if number is not None:
            if selected_categories is None:
                data = get_queue(guild_id, number)
            else:
                data = []
                for category_name in selected_categories:
                    data.extend(get_queue(guild_id, number, category_name))
        else:
            if selected_categories is None:
                data = get_all_queue(guild_id)
            else:
                data = []
                for category_name in selected_categories:
                    data.extend(get_all_queue(guild_id, category_name))

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

            await interaction.response.send_message(
                message,
                ephemeral=number is not None,
            )
            return

        queues = {}
        for row in data:
            queue_no = row["queue_no"]
            row_category = row["category"]
            reward_type = row["reward_type"]
            group_key = ("LINKED", queue_no) if row_category in LINKED else (row_category, queue_no)
            (
                queues.setdefault(group_key, {})
                .setdefault(row_category, {})
                .setdefault(reward_type, [])
                .append(row)
            )

        embeds = []
        MAX_FIELDS = 20
        MAX_EMBED_CHARS = 5500
        MAX_FIELD_VALUE = 1024

        def create_embed(title, continued=False):
            if continued:
                title = f"{title} • Continued"
            return discord.Embed(title=title, description="Auction Queue List")

        def embed_size(embed):
            size = len(embed.title or "") + len(embed.description or "")
            for field in embed.fields:
                size += len(field.name) + len(field.value)
            return size

        def split_value(value, max_length=MAX_FIELD_VALUE):
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
            separator = "────────────────────"
            queue_value = f"{value}\n\n{separator}" if value else separator
            values = split_value(queue_value)

            for index, field_value in enumerate(values):
                field_name = (
                    f"📋 Queue #{queue_no}"
                    if index == 0
                    else f"↳ Queue #{queue_no} (continued)"
                )
                estimated_size = embed_size(current_embed) + len(field_name) + len(field_value)

                if len(current_embed.fields) >= MAX_FIELDS or estimated_size >= MAX_EMBED_CHARS:
                    if current_embed.fields:
                        embed_list.append(current_embed)
                    current_embed = create_embed(embed_title, continued=True)

                current_embed.add_field(
                    name=field_name,
                    value=field_value,
                    inline=False,
                )

            return current_embed

        linked_keys = [key for key in queues if key[0] == "LINKED"]
        if linked_keys:
            embed_title = "🏆 Guild League / League Prize"
            embed = create_embed(embed_title)

            for _, queue_no in sorted(linked_keys, key=lambda x: x[1]):
                category_groups = queues[("LINKED", queue_no)]
                value_lines = []

                for linked_category in LINKED:
                    reward_groups = category_groups.get(linked_category)
                    if not reward_groups:
                        continue
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

        for independent_category in (
            "Emperium Overrun",
            "Designed Auction",
        ):
            category_keys = [key for key in queues if key[0] == independent_category]
            if not category_keys:
                continue

            embed_title = f"📂 {independent_category}"
            embed = create_embed(embed_title)

            for _, queue_no in sorted(category_keys, key=lambda x: x[1]):
                category_groups = queues[(independent_category, queue_no)]
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

        if not embeds:
            await interaction.response.send_message("❌ No queue data found.")
            return

        is_ephemeral = number is not None

        await interaction.response.send_message(
            embed=embeds[0],
            ephemeral=is_ephemeral,
        )

        for embed in embeds[1:]:
            await interaction.followup.send(
                embed=embed,
                ephemeral=is_ephemeral,
            )


async def setup(bot):
    await bot.add_cog(Queue(bot))
