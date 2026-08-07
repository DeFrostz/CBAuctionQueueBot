import discord

from discord.ext import commands

import asyncio

from database import (
    set_reward_stock,
    set_reward_limit,
    get_rewards,
    clear_queue,
    clear_rewards,
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

        category_value = category.value if category is not None else "All"

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
            # =================================
            # Clear only categories being generated
            # =================================

            for cat in valid_categories:
                clear_queue(guild_id, cat)

            results = {}

            category_rewards = {}
            normal_queue_counts = {}

            # GL + LP share this counter only
            linked_next_queue_no = 1

            # =================================
            # Generate normal queues
            # =================================

            for cat in valid_categories:
                rows = get_rewards(guild_id, cat)

                category_rewards[cat] = rows

                # -----------------------------
                # Guild League + League Prize
                # share queue numbering
                # -----------------------------

                if cat in LINKED:
                    start_no = linked_next_queue_no

                    count = await asyncio.to_thread(
                        generate_queue, guild_id, rows, start_no
                    )

                    linked_next_queue_no += count

                # -----------------------------
                # Independent categories
                # always start from Queue 1
                # -----------------------------

                else:
                    start_no = 1

                    count = await asyncio.to_thread(
                        generate_queue, guild_id, rows, start_no
                    )

                normal_queue_counts[cat] = count

                results[cat] = {
                    "count": count,
                    "start": start_no,
                    "end": (start_no + count - 1 if count > 0 else 0),
                }

            # =================================
            # GL + LP Extra Pool
            # =================================

            extra_count = 0
            remaining_extra = None
            extra_start = None

            if all(cat in category_rewards for cat in LINKED):
                extra_pool = build_extra_pool(
                    {cat: category_rewards[cat] for cat in LINKED},
                    {cat: normal_queue_counts[cat] for cat in LINKED},
                )

                # GL + LP limits are linked,
                # so use GL limits
                linked_reward_map = {
                    row["reward_type"]: row for row in category_rewards[LINKED[0]]
                }

                limits = {
                    reward: linked_reward_map[reward]["limit_per_queue"]
                    for reward in required
                }

                extra_start = linked_next_queue_no

                extra_count, remaining_extra = await asyncio.to_thread(
                    generate_extra_queues,
                    guild_id,
                    extra_pool,
                    limits,
                    linked_next_queue_no,
                )

                linked_next_queue_no += extra_count

            # =================================
            # Response
            # =================================
            lines = ["✅ Queue Generated", ""]

            # -------------------------
            # Guild League + League Prize
            # -------------------------

            if any(cat in results for cat in LINKED):
                lines.append("🏆 Guild League / League Prize")

                for cat in LINKED:
                    if cat not in results:
                        continue

                    data = results[cat]

                    if data["count"] > 0:
                        lines.append(
                            f"- {cat}: "
                            f"{data['count']} "
                            f"(Queue {data['start']}-{data['end']})"
                        )

            # -------------------------
            # Independent Categories
            # -------------------------

            for cat in (
                "Emperium Overrun",
                "Designed Auction",
            ):
                if cat not in results:
                    continue

                data = results[cat]

                lines.append("")
                lines.append(f"📂 {cat}")

                if data["count"] > 0:
                    lines.append(
                        f"- {data['count']} (Queue {data['start']}-{data['end']})"
                    )
                else:
                    lines.append("- 0")

            # Extra belongs only to GL + LP
            if extra_count > 0:
                lines.append(
                    f"- GL/LP Extra: "
                    f"{extra_count} "
                    f"(Queue "
                    f"{extra_start}-"
                    f"{linked_next_queue_no - 1})"
                )

            # Skipped categories
            if skipped_categories:
                lines.append("")
                lines.append("Skipped:")

                for cat, reason in skipped_categories:
                    lines.append(f"- {cat}: {reason}")

            # Remaining linked extra
            if remaining_extra is not None:
                lines.extend(
                    [
                        "",
                        "Remaining GL/LP Extra:",
                        f"- Card: {remaining_extra['CARD']}",
                        f"- Light-Dark: {remaining_extra['FEATHER_S']}",
                        f"- Time-Space: {remaining_extra['FEATHER_A']}",
                    ]
                )

            total_generated = (
                sum(data["count"] for data in results.values()) + extra_count
            )

            lines.extend(
                [
                    "",
                    f"Total generated queues: {total_generated}",
                    "",
                    "Use: /queuelist",
                ]
            )

            await interaction.followup.send("\n".join(lines))
        except Exception as e:
            print("Error generating queues:", e)

            await interaction.followup.send(f"❌ Failed to generate queue: {e}")


    # -----------------------------
    # /clearconfig
    # -----------------------------
    
    @discord.app_commands.command(
        name="clearconfig",
        description="Clear stock, limits and generated queues",
    )
    @discord.app_commands.choices(
        category=[
            discord.app_commands.Choice(name=cat, value=cat)
            for cat in (*CATEGORIES, "All")
        ]
    )
    async def clearconfig(
        self,
        interaction: discord.Interaction,
        category: discord.app_commands.Choice[str] | None = None,
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used in a server.",
                ephemeral=True,
            )
            return
    
        guild_id = str(interaction.guild.id)
    
        category_value = (
            category.value
            if category is not None
            else "All"
        )
    
        if category_value == "All":
            targets = list(CATEGORIES)
    
        elif category_value in LINKED:
            targets = list(LINKED)
    
        else:
            targets = [category_value]
    
        for target in targets:
            clear_rewards(
                guild_id,
                target,
            )
    
            clear_queue(
                guild_id,
                target,
            )
    
        await interaction.response.send_message(
            "✅ Configuration cleared\n\n"
            f"Category: {', '.join(targets)}"
        )

async def setup(bot):
    await bot.add_cog(Admin(bot))
