import discord

from discord.ext import commands

import asyncio

from database import (
    set_reward_stock,
    set_reward_limit,
    get_rewards,
    clear_queue,
    CATEGORIES,
)

from generator import generate_queue, build_extra_pool, generate_extra_queues

LINKED = ("Guild League", "League Prize")


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def reward_name(reward):
        return {
            "CARD": "Card",
            "FEATHER_S": "Light-Dark",
            "FEATHER_A": "Time-Space",
        }.get(reward, reward)

    @discord.app_commands.command(
        name="setallstock", description="Set stock for all three rewards at once"
    )
    @discord.app_commands.choices(
        category=[
            discord.app_commands.Choice(name=cat, value=cat)
            for cat in (*CATEGORIES, "All")
        ]
    )
    @discord.app_commands.describe(
        card="Total Card stock",
        light_dark="Total Light-Dark stock",
        time_space="Total Time-Space stock",
        category="Which category to apply (Guild League default)",
    )
    async def setallstock(
        self,
        interaction: discord.Interaction,
        card: int,
        light_dark: int,
        time_space: int,
        category: discord.app_commands.Choice[str] | None = None,
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used in a server"
            )
            return

        stock_values = {"CARD": card, "FEATHER_S": light_dark, "FEATHER_A": time_space}

        if any(stock < 0 for stock in stock_values.values()):
            await interaction.response.send_message(
                "❌ Stock must be 0 or greater for all rewards"
            )
            return

        guild_id = str(interaction.guild.id)
        category_value = category.value if category is not None else "All"
        targets = []
        if category_value == "All":
            targets = list(CATEGORIES)
        else:
            targets = [category_value]

        for target in targets:
            for reward, stock in stock_values.items():
                set_reward_stock(guild_id, reward, stock, target)

        await interaction.response.send_message(
            "✅ All reward stock updated\n"
            f"🃏 Card: {card}\n"
            f"🌗 Light-Dark: {light_dark}\n"
            f"⏳ Time-Space: {time_space}\n"
            f"Applied to: {', '.join(targets)}"
        )

    @discord.app_commands.command(
        name="setalllimit", description="Set limits for all three rewards at once"
    )
    @discord.app_commands.choices(
        category=[
            discord.app_commands.Choice(name=cat, value=cat)
            for cat in (*CATEGORIES, "All")
        ]
    )
    @discord.app_commands.describe(
        card="Card amount per queue",
        light_dark="Light-Dark amount per queue",
        time_space="Time-Space amount per queue",
        category="Which category to apply (Guild League default). Guild League and League Prize are linked.",
    )
    async def setalllimit(
        self,
        interaction: discord.Interaction,
        card: int,
        light_dark: int,
        time_space: int,
        category: discord.app_commands.Choice[str] | None = None,
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used in a server"
            )
            return

        limit_values = {"CARD": card, "FEATHER_S": light_dark, "FEATHER_A": time_space}

        if any(limit < 1 for limit in limit_values.values()):
            await interaction.response.send_message(
                "❌ Every limit must be 1 or greater"
            )
            return

        guild_id = str(interaction.guild.id)
        category_value = category.value if category is not None else CATEGORIES[0]

        targets = []
        if category_value == "All":
            targets = list(CATEGORIES)
        elif category_value in LINKED:
            targets = list(LINKED)
        else:
            targets = [category_value]

        for target in targets:
            for reward, limit in limit_values.items():
                set_reward_limit(guild_id, reward, limit, target)

        await interaction.response.send_message(
            "✅ All queue limits updated\n"
            f"🃏 Card: {card}\n"
            f"🌗 Light-Dark: {light_dark}\n"
            f"⏳ Time-Space: {time_space}\n"
            f"Applied to: {', '.join(targets)}"
        )

    # -----------------------------
    # /clearqueues
    # -----------------------------

    @discord.app_commands.command(
        name="clearqueues", description="Clear generated auction queues"
    )
    @discord.app_commands.choices(
        category=[
            discord.app_commands.Choice(name=cat, value=cat)
            for cat in (*CATEGORIES, "All")
        ]
    )
    @discord.app_commands.describe(category="Which category to clear, or All")
    async def clearqueues(
        self,
        interaction: discord.Interaction,
        category: discord.app_commands.Choice[str] | None = None,
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used in a server", ephemeral=True
            )
            return

        # Security check
        if not (
            interaction.user.guild_permissions.administrator
            or await self.bot.is_owner(interaction.user)
        ):
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command.",
                ephemeral=True,
            )
            return

        guild_id = str(interaction.guild.id)

        category_value = category.value if category is not None else "All"

        if category_value == "All":
            clear_queue(guild_id)
            message = "all categories"
        else:
            clear_queue(guild_id, category_value)
            message = f"**{category_value}**"

        await interaction.response.send_message(f"🗑️ Cleared queues for {message}.")

    # -----------------------------
    # /generate
    # -----------------------------
    @discord.app_commands.command(name="generate", description="Generate auction queue")
    @discord.app_commands.choices(
        category=[
            discord.app_commands.Choice(name=cat, value=cat)
            for cat in (*CATEGORIES, "All")
        ]
    )
    async def generate(
        self,
        interaction: discord.Interaction,
        category: discord.app_commands.Choice[str] | None = None,
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used in a server"
            )
            return

        guild_id = str(interaction.guild.id)

        category_value = category.value if category is not None else CATEGORIES[0]

        if category_value == "All":
            to_generate = list(CATEGORIES)

        elif category_value in LINKED:
            # GL + LP always generate together
            to_generate = list(LINKED)

        else:
            to_generate = [category_value]

        required = ("CARD", "FEATHER_S", "FEATHER_A")

        valid_categories = []
        skipped_categories = []

        for cat in to_generate:
            rows = get_rewards(guild_id, cat)

            reward_map = {row["reward_type"]: row for row in rows}

            # ต้องมี reward ครบ 3 ตัว
            if any(reward not in reward_map for reward in required):
                skipped_categories.append((cat, "missing reward config"))
                continue

            # limit ต้อง > 0 ครบทุกตัว
            if any(
                int(reward_map[reward]["limit_per_queue"]) < 1 for reward in required
            ):
                skipped_categories.append((cat, "missing limit"))
                continue

            # stock ต้อง > 0 ครบทุกตัว
            if any(int(reward_map[reward]["stock"]) < 1 for reward in required):
                skipped_categories.append((cat, "missing stock"))
                continue

            valid_categories.append(cat)

        if not valid_categories:
            lines = ["❌ No categories are ready to generate."]

            if skipped_categories:
                lines.append("")
                lines.append("Skipped:")

                for cat, reason in skipped_categories:
                    lines.append(f"- {cat}: {reason}")

            await interaction.response.send_message("\n".join(lines))

            return

        await interaction.response.defer(thinking=True)

        try:
            # Remove previous generated queues
            for cat in valid_categories:
                clear_queue(guild_id, cat)

            results = {}

            next_queue_no = 1

            category_rewards = {}

            normal_queue_counts = {}

            # =================================
            # Generate normal category queues
            # =================================

            for cat in valid_categories:
                rows = get_rewards(guild_id, cat)

                category_rewards[cat] = rows

                count = await asyncio.to_thread(
                    generate_queue, guild_id, rows, next_queue_no
                )

                normal_queue_counts[cat] = count

                start = next_queue_no

                next_queue_no += count

                results[cat] = {
                    "count": count,
                    "start": start,
                    "end": next_queue_no - 1,
                }

            extra_count = 0

            remaining_extra = None

            # =================================
            # GL + LP Extra Pool
            # =================================

            if all(cat in category_rewards for cat in LINKED):
                extra_pool = build_extra_pool(
                    {cat: category_rewards[cat] for cat in LINKED},
                    {cat: normal_queue_counts[cat] for cat in LINKED},
                )

                # Limits are linked,
                # so GL limits can be used.
                linked_reward_map = {
                    row["reward_type"]: row for row in category_rewards[LINKED[0]]
                }

                limits = {
                    reward: linked_reward_map[reward]["limit_per_queue"]
                    for reward in required
                }

                extra_count, remaining_extra = await asyncio.to_thread(
                    generate_extra_queues, guild_id, extra_pool, limits, next_queue_no
                )

                extra_start = next_queue_no

                next_queue_no += extra_count

            # =================================
            # Response
            # =================================

            lines = ["✅ Queue Generated", "", "Total queues per category:"]

            for cat, data in results.items():
                if data["count"] > 0:
                    lines.append(
                        f"- {cat}: "
                        f"{data['count']} "
                        f"(Queue "
                        f"{data['start']}-"
                        f"{data['end']})"
                    )

                else:
                    lines.append(f"- {cat}: 0")

            if skipped_categories:
                lines.append("")
                lines.append("Skipped:")

            for cat, reason in skipped_categories:
                lines.append(f"- {cat}: {reason}")

            if extra_count > 0:
                lines.append(
                    f"- Extra: {extra_count} (Queue {extra_start}-{next_queue_no - 1})"
                )

            if remaining_extra is not None:
                lines.extend(
                    [
                        "",
                        "Remaining Extra:",
                        f"- Card: {remaining_extra['CARD']}",
                        f"- Light-Dark: {remaining_extra['FEATHER_S']}",
                        f"- Time-Space: {remaining_extra['FEATHER_A']}",
                    ]
                )

            lines.extend(
                ["", f"Total queues: {next_queue_no - 1}", "", "Use: /queuelist"]
            )

            await interaction.followup.send("\n".join(lines))

        except Exception as e:
            print("Error generating queues:", e)

            await interaction.followup.send(f"❌ Failed to generate queue: {e}")


async def setup(bot):
    await bot.add_cog(Admin(bot))
