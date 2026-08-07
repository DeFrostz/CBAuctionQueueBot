import discord

from discord.ext import commands

from database import get_all_queue, get_queue, get_queue_count, get_rewards, CATEGORIES


class Queue(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def group_slots(self, rows):
        """
        รวม Slot ที่อยู่ Page เดียวกัน

        เช่น

        Page 1
        Slot 1
        Slot 2
        Slot 3

        กลายเป็น

        Page 1 : Slot 1-3
        """

        pages = {}

        for row in rows:
            page = row["page"]
            slot = row["slot"]

            if page not in pages:
                pages[page] = []

            pages[page].append(slot)

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

    @discord.app_commands.command(
        name="extra", description="View rewards that are not assigned to a queue"
    )
    async def extra(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used in a server"
            )
            return

        guild_id = str(interaction.guild.id)

        reward_order = ("CARD", "FEATHER_S", "FEATHER_A")

        reward_names = {
            "CARD": "🃏 Card",
            "FEATHER_S": "🌗 Light-Dark",
            "FEATHER_A": "⏳ Time-Space",
        }

        embed = discord.Embed(
            title="📦 Extra Rewards", description="Rewards not assigned to queues"
        )

        for category in CATEGORIES:
            rewards = {
                row["reward_type"]: row for row in get_rewards(guild_id, category)
            }

            queue_count = get_queue_count(guild_id, category)

            category_lines = [f"**Queues: {queue_count}**"]

            for reward in reward_order:
                row = rewards.get(reward)

                if row is None:
                    category_lines.append(f"{reward_names[reward]}\nNot configured")
                    continue

                assigned = queue_count * row["limit_per_queue"]

                extra = max(row["stock"] - assigned, 0)

                if extra == 0:
                    positions = "None"

                else:
                    start_index = assigned

                    # Feather A starts after all Feather S
                    if reward == "FEATHER_A":
                        feather_s = rewards.get("FEATHER_S")

                        start_index = (
                            feather_s["stock"] if feather_s else 0
                        ) + assigned

                    positions = self.group_position_range(start_index, extra)

                category_lines.append(
                    f"{reward_names[reward]}\n"
                    f"Stock: {row['stock']}\n"
                    f"In queues: {assigned}\n"
                    f"Extra: **{extra}**\n"
                    f"Positions:\n{positions}"
                )

            embed.add_field(
                name=f"📂 {category}", value="\n\n".join(category_lines), inline=False
            )

        await interaction.response.send_message(embed=embed)

    @discord.app_commands.command(
        name="queuelist", description="View queues by number and/or category"
    )
    @discord.app_commands.choices(
        category=[
            discord.app_commands.Choice(name=cat, value=cat) for cat in CATEGORIES
        ]
    )
    @discord.app_commands.describe(
        number="Optional queue number", category="Optional category"
    )
    async def queue(
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

        category_value = category.value if category is not None else None

        if number is not None:
            data = get_queue(guild_id, number, category_value)

        else:
            data = get_all_queue(guild_id, category_value)

        if not data:
            if number is not None and category_value is not None:
                message = f"❌ Queue #{number} not found in **{category_value}**"

            elif number is not None:
                message = f"❌ Queue #{number} not found"

            elif category_value is not None:
                message = f"❌ No queues found for **{category_value}**"

            else:
                message = "❌ No queues generated yet. Use `/generate` first."

            await interaction.response.send_message(message)

            return

        name_map = {
            "CARD": "🃏 Card",
            "FEATHER_S": "🌗 Light-Dark",
            "FEATHER_A": "⏳ Time-Space",
        }
        reward_order = ("CARD", "FEATHER_S", "FEATHER_A")
        # Group by queue_no first.
        # One Extra queue can contain positions
        # from both Guild League and League Prize.
        queues = {}

        for row in data:
            queue_no = row["queue_no"]
            category = row["category"]

            queues.setdefault(queue_no, {}).setdefault(category, {}).setdefault(
                row["reward_type"], []
            ).append(row)

        sections = []

        for queue_no in sorted(queues):
            category_groups = queues[queue_no]

            lines = [f"📋 Queue #{queue_no}"]

            for category, reward_groups in category_groups.items():
                lines.append(f"\n**{category}**")

                for reward in reward_order:
                    rows = reward_groups.get(reward)

                    if not rows:
                        continue

                    lines.append(name_map.get(reward, reward))

                    lines.extend(
                        f"- {position}"
                        for position in self.group_slots(rows).splitlines()
                    )

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
