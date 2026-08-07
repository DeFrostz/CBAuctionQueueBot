import discord

from discord.ext import commands

import asyncio

from database import (
    set_reward_stock,
    set_reward_limit,
    get_rewards,
    CATEGORIES,
)
from generator import generate_queue


LINKED = ("Guild League", "League Prize")


class Admin(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def reward_name(reward):
        return {
            "CARD": "Card",
            "FEATHER_S": "Light-Dark",
            "FEATHER_A": "Time-Space"
        }.get(reward, reward)


    @discord.app_commands.command(
        name="setallstock",
        description="Set stock for all three rewards at once"
    )
    @discord.app_commands.choices(
        category=[
            discord.app_commands.Choice(name=cat, value=cat) for cat in (*CATEGORIES, "All")
        ]
    )
    @discord.app_commands.describe(
        card="Total Card stock",
        light_dark="Total Light-Dark stock",
        time_space="Total Time-Space stock",
        category="Which category to apply (Guild League default)"
    )
    async def setallstock(
        self,
        interaction: discord.Interaction,
        card: int,
        light_dark: int,
        time_space: int,
        category: discord.app_commands.Choice[str] | None = None
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used in a server"
            )
            return

        stock_values = {
            "CARD": card,
            "FEATHER_S": light_dark,
            "FEATHER_A": time_space
        }

        if any(stock < 0 for stock in stock_values.values()):
            await interaction.response.send_message(
                "❌ Stock must be 0 or greater for all rewards"
            )
            return

        guild_id = str(interaction.guild.id)
        category_value = (category.value if category is not None else CATEGORIES[0])

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
        name="setalllimit",
        description="Set limits for all three rewards at once"
    )
    @discord.app_commands.choices(
        category=[
            discord.app_commands.Choice(name=cat, value=cat) for cat in (*CATEGORIES, "All")
        ]
    )
    @discord.app_commands.describe(
        card="Card amount per queue",
        light_dark="Light-Dark amount per queue",
        time_space="Time-Space amount per queue",
        category="Which category to apply (Guild League default). Guild League and League Prize are linked."
    )
    async def setalllimit(
        self,
        interaction: discord.Interaction,
        card: int,
        light_dark: int,
        time_space: int,
        category: discord.app_commands.Choice[str] | None = None
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used in a server"
            )
            return

        limit_values = {
            "CARD": card,
            "FEATHER_S": light_dark,
            "FEATHER_A": time_space
        }

        if any(limit < 1 for limit in limit_values.values()):
            await interaction.response.send_message(
                "❌ Every limit must be 1 or greater"
            )
            return

        guild_id = str(interaction.guild.id)
        category_value = (category.value if category is not None else CATEGORIES[0])

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


    @discord.app_commands.command(
        name="setstock",
        description="Set the total stock for a reward"
    )
    @discord.app_commands.choices(
        reward=[
            discord.app_commands.Choice(name="Card", value="CARD"),
            discord.app_commands.Choice(name="Light-Dark", value="FEATHER_S"),
            discord.app_commands.Choice(name="Time-Space", value="FEATHER_A"),
        ],
        category=[
            discord.app_commands.Choice(name=cat, value=cat) for cat in CATEGORIES
        ]
    )
    @discord.app_commands.describe(
        reward="Choose one of the 3 rewards",
        stock="Total amount available",
        category="Which category to set (Guild League default)"
    )
    async def setstock(
        self,
        interaction: discord.Interaction,
        reward: discord.app_commands.Choice[str],
        stock: int,
        category: discord.app_commands.Choice[str] | None = None
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used in a server"
            )
            return

        guild_id = str(interaction.guild.id)
        reward = reward.value
        category_value = (category.value if category is not None else CATEGORIES[0])

        if reward not in ("CARD", "FEATHER_S", "FEATHER_A"):
            await interaction.response.send_message(
                "❌ Reward type incorrect"
            )
            return

        if stock < 0:
            await interaction.response.send_message(
                "❌ Stock must be 0 or greater"
            )
            return

        set_reward_stock(
            guild_id,
            reward,
            stock,
            category_value
        )

        await interaction.response.send_message(
            f"✅ {self.reward_name(reward)} stock updated to {stock} for {category_value}\n"
            "Use `/setlimit` to change the limit per queue."
        )

    @discord.app_commands.command(
        name="setlimit",
        description="Set the reward limit per queue"
    )
    @discord.app_commands.choices(
        reward=[
            discord.app_commands.Choice(name="Card", value="CARD"),
            discord.app_commands.Choice(name="Light-Dark", value="FEATHER_S"),
            discord.app_commands.Choice(name="Time-Space", value="FEATHER_A"),
        ],
        category=[
            discord.app_commands.Choice(name=cat, value=cat) for cat in (*CATEGORIES,)
        ]
    )
    @discord.app_commands.describe(
        reward="Choose one of the 3 rewards",
        limit="Amount used in each queue",
        category="Which category to set (Guild League default). Guild League and League Prize are linked."
    )
    async def setlimit(
        self,
        interaction: discord.Interaction,
        reward: discord.app_commands.Choice[str],
        limit: int,
        category: discord.app_commands.Choice[str] | None = None
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used in a server"
            )
            return

        guild_id = str(interaction.guild.id)
        reward = reward.value
        category_value = (category.value if category is not None else CATEGORIES[0])

        if reward not in ("CARD", "FEATHER_S", "FEATHER_A"):
            await interaction.response.send_message(
                "❌ Reward type incorrect"
            )
            return

        if limit < 1:
            await interaction.response.send_message(
                "❌ Limit per queue must be 1 or greater"
            )
            return

        # If setting for Guild League OR League Prize, set both to keep them equal
        if category_value in LINKED:
            for cat in LINKED:
                set_reward_limit(
                    guild_id,
                    reward,
                    limit,
                    cat
                )
            applied = ", ".join(LINKED)
        else:
            set_reward_limit(
                guild_id,
                reward,
                limit,
                category_value
            )
            applied = category_value

        await interaction.response.send_message(
            f"✅ {self.reward_name(reward)} limit per queue updated to {limit} for {applied}\n"
            "Use `/setstock` to change the total stock."
        )

    # -----------------------------
    # /generate
    # -----------------------------

    @discord.app_commands.command(
        name="generate",
        description="Generate auction queue"
    )
    @discord.app_commands.choices(
        category=[
            discord.app_commands.Choice(name=cat, value=cat) for cat in (*CATEGORIES, "All")
        ]
    )
    async def generate(
        self,
        interaction: discord.Interaction,
        category: discord.app_commands.Choice[str] | None = None
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used in a server"
            )
            return

        guild_id = str(interaction.guild.id)
        category_value = (category.value if category is not None else CATEGORIES[0])

        # Determine which categories we will generate (for validation)
        if category_value == "All":
            to_generate = list(CATEGORIES)
        elif category_value in LINKED:
            to_generate = list(LINKED)
        else:
            to_generate = [category_value]

        # Validate each category has limits/configured
        for cat in to_generate:
            rows = get_rewards(guild_id, cat)
            reward_map = {row["reward_type"]: row for row in rows}
            required = ("CARD", "FEATHER_S", "FEATHER_A")
            if any(r not in reward_map for r in required) or any(reward_map[r]["limit_per_queue"] < 1 for r in required):
                await interaction.response.send_message(
                    "❌ Please set stock and a limit of 1 or more for all rewards first\n\nUse:\n/setstock <reward> <stock> <category>\n/setlimit <reward> <limit> <category>"
                )
                return

        # Acknowledge interaction to avoid Discord timeout and run generation in background
        await interaction.response.defer(thinking=True)

        # Run generator per category in a thread to avoid blocking the event loop
        results = {}
        try:
            for cat in to_generate:
                rows = get_rewards(guild_id, cat)
                cnt = await asyncio.to_thread(generate_queue, guild_id, rows)
                results[cat] = cnt
        except Exception as e:
            print("Error generating queues:", e)
            await interaction.followup.send(f"❌ Failed to generate queue: {e}")
            return

        # Build reply text
        lines = ["✅ Queue Generated", "", "Total queues per category:"]
        for cat, cnt in results.items():
            lines.append(f"- {cat}: {cnt}")

        lines.append("")
        lines.append("Use: /queue <number> to view queue")

        await interaction.followup.send("\n".join(lines))


async def setup(bot):
    await bot.add_cog(Admin(bot))
