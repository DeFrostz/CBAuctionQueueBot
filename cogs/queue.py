import discord

from discord.ext import commands

from database import (
    get_all_queue,
    get_queue,
    get_queue_count,
    get_rewards,
    get_assigned_count,
    CATEGORIES,
)


class Queue(commands.Cog):

    def __init__(self, bot):
        self.bot = bot


    def group_slots(self, rows):
        """
        Group slots that are on the same page into a compact range text.
        """
        pages = {}
        for row in rows:
            page = row["page"]
            slot = row["slot"]
            pages.setdefault(page, []).append(slot)

        result = []
        for page, slots in pages.items():
            slots.sort()
            if len(slots) == 1:
                slot_text = str(slots[0])
            else:
                slot_text = f"{slots[0]}-{slots[-1]}"
            result.append(f"Page {page} : Slot {slot_text}")

        return "\n".join(result)

    def group_position_range(self, start_index, amount):
        pages = {}

        for index in range(start_index, start_index + amount):
            page = index // 4 + 1
            slot = index % 4 + 1
            pages.setdefault(page, []).append(slot)

        result = []
        for page, slots in pages.items():
            if len(slots) == 1:
                slot_text = str(slots[0])
            else:
                slot_text = f"{slots[0]}-{slots[-1]}"

            result.append(f"Page {page} : Slot {slot_text}")

        return "\n".join(result)

    def group_positions_explicit(self, start_index, amount):
        """
        Return explicit Page/Slot entries for each item (no ranges).
        """
        lines = []
        for index in range(start_index, start_index + amount):
            page = index // 4 + 1
            slot = index % 4 + 1
            lines.append(f"Page {page} : Slot {slot}")
        return "\n".join(lines) if lines else "None"

    @discord.app_commands.command(
        name="extra",
        description="View rewards that are not assigned to a queue"
    )
    @discord.app_commands.choices(
        category=[discord.app_commands.Choice(name=cat, value=cat) for cat in (*CATEGORIES, "All")]
    )
    async def extra(self, interaction: discord.Interaction, category: discord.app_commands.Choice[str] | None = None):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used in a server"
            )
            return

        guild_id = str(interaction.guild.id)
        category_value = (category.value if category is not None else CATEGORIES[0])

        # If All, show extras grouped per category
        categories = list(CATEGORIES) if category_value == "All" else [category_value]

        embed = discord.Embed(title="📦 Extra Rewards")

        for cat in categories:
            rewards = {row["reward_type"]: row for row in get_rewards(guild_id, cat)}
            # Use assigned count from DB per category+reward instead of global queue_count * limit
            reward_order = ("CARD", "FEATHER_S", "FEATHER_A")
            reward_names = {
                "CARD": "🃏 Card",
                "FEATHER_S": "🌗 Light-Dark",
                "FEATHER_A": "⏳ Time-Space"
            }

            lines = [f"Category: {cat}"]

            for reward in reward_order:
                row = rewards.get(reward)
                if row is None:
                    value = "Not configured"
                else:
                    # actual assigned slots for this guild/category/reward
                    assigned = get_assigned_count(guild_id, cat, reward)
                    extra = max(row["stock"] - assigned, 0)
                    if extra == 0:
                        positions = "None"
                    else:
                        start_index = assigned
                        # Use explicit positions (one line per item) so staff can see exact slot numbers
                        positions = self.group_positions_explicit(start_index, extra)

                    value = (
                        f"Stock: {row['stock']}\n"
                        f"In queues: {assigned}\n"
                        f"Extra: **{extra}**\n"
                        f"Positions:\n{positions}"
                    )

                lines.append(f"{reward_names[reward]}:\n{value}")

            embed.add_field(name=cat, value="\n".join(lines), inline=False)

        await interaction.response.send_message(embed=embed)

    @discord.app_commands.command(
        name="queuelist",
        description="View all queues or one specific queue"
    )
    @discord.app_commands.describe(
        number="Optional queue number to view only that queue",
        category="Optional category to filter by (Guild League default). Use All to view all categories."
    )
    @discord.app_commands.choices(
        category=[discord.app_commands.Choice(name=cat, value=cat) for cat in (*CATEGORIES, "All")]
    )
    async def queue(self, interaction: discord.Interaction, number: int | None = None, category: discord.app_commands.Choice[str] | None = None):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used in a server"
            )
            return

        guild_id = str(interaction.guild.id)
        category_value = (category.value if category is not None else CATEGORIES[0])

        if number is not None:
            data = get_queue(guild_id, number)
        else:
            data = get_all_queue(guild_id)

        if not data:
            await interaction.response.send_message(
                (
                    f"❌ Queue #{number} not found"
                    if number is not None
                    else "❌ No queues generated yet. Use `/generate` first."
                )
            )
            return

        name_map = {
            "CARD": "🃏 Card",
            "FEATHER_S": "🌗 Light-Dark",
            "FEATHER_A": "⏳ Time-Space"
        }
        reward_order = ("CARD", "FEATHER_S", "FEATHER_A")

        # Filter by category if requested
        if category_value != "All":
            data = [row for row in data if row["category"] == category_value]

        queues = {}
        for row in data:
            queues.setdefault(row["queue_no"], {}).setdefault(
                (row["category"], row["reward_type"]), []
            ).append(row)

        sections = []
        for queue_no, reward_groups in queues.items():
            lines = [f"📋 Queue #{queue_no}"]
            # group by category then by reward_order
            grouped_by_cat = {}
            for (cat, reward), rows in reward_groups.items():
                grouped_by_cat.setdefault(cat, {}).setdefault(reward, []).extend(rows)

            for cat in grouped_by_cat:
                lines.append(f"\nCategory: {cat}")
                for reward in reward_order:
                    rows = grouped_by_cat[cat].get(reward)
                    if not rows:
                        continue
                    lines.append(name_map.get(reward, reward))
                    lines.extend(f"- {position}" for position in self.group_slots(rows).splitlines())
            sections.append("\n".join(lines))

        chunks = []
        current = ""
        for section in sections:
            candidate = f"{current}\n\n{section}".strip()
            if current and len(candidate) > 1900:
                chunks.append(current)
                current = section
            else:
                current = candidate
        if current:
            chunks.append(current)

        await interaction.response.send_message(chunks[0])
        for chunk in chunks[1:]:
            await interaction.followup.send(chunk)


async def setup(bot):
    await bot.add_cog(Queue(bot))
