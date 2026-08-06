import discord

from discord.ext import commands

from database import (
    set_reward_stock,
    set_reward_limit,
    get_rewards
)

from generator import (
    generate_queue
)


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
        name="setstock",
        description="Set the total stock for a reward"
    )
    @discord.app_commands.choices(
        reward=[
            discord.app_commands.Choice(
                name="Card",
                value="CARD"
            ),
            discord.app_commands.Choice(
                name="Light-Dark",
                value="FEATHER_S"
            ),
            discord.app_commands.Choice(
                name="Time-Space",
                value="FEATHER_A"
            )
        ]
    )
    @discord.app_commands.describe(
        reward="Choose one of the 3 rewards",
        stock="Total amount available"
    )
    async def setstock(
        self,
        interaction: discord.Interaction,
        reward: discord.app_commands.Choice[str],
        stock: int
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used in a server"
            )
            return

        guild_id = str(interaction.guild.id)
        reward = reward.value

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
            stock
        )

        await interaction.response.send_message(
            f"✅ {self.reward_name(reward)} stock updated to {stock}\n"
            "Use `/setlimit` to change the limit per queue."
        )

    @discord.app_commands.command(
        name="setlimit",
        description="Set the reward limit per queue"
    )
    @discord.app_commands.choices(
        reward=[
            discord.app_commands.Choice(
                name="Card",
                value="CARD"
            ),
            discord.app_commands.Choice(
                name="Light-Dark",
                value="FEATHER_S"
            ),
            discord.app_commands.Choice(
                name="Time-Space",
                value="FEATHER_A"
            )
        ]
    )
    @discord.app_commands.describe(
        reward="Choose one of the 3 rewards",
        limit="Amount used in each queue"
    )
    async def setlimit(
        self,
        interaction: discord.Interaction,
        reward: discord.app_commands.Choice[str],
        limit: int
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used in a server"
            )
            return

        guild_id = str(interaction.guild.id)
        reward = reward.value

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

        set_reward_limit(
            guild_id,
            reward,
            limit
        )

        await interaction.response.send_message(
            f"✅ {self.reward_name(reward)} limit per queue updated to {limit}\n"
            "Use `/setstock` to change the total stock."
        )

    # -----------------------------
    # /generate
    # -----------------------------

    @discord.app_commands.command(
        name="generate",
        description="Generate auction queue"
    )
    async def generate(

        self,

        interaction: discord.Interaction

    ):


        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used in a server"
            )
            return

        guild_id = str(interaction.guild.id)


        rewards = get_rewards(
            guild_id
        )


        reward_map = {
            row["reward_type"]: row
            for row in rewards
        }
        required_rewards = ("CARD", "FEATHER_S", "FEATHER_A")

        if (
            any(reward not in reward_map for reward in required_rewards)
            or any(
                reward_map[reward]["limit_per_queue"] < 1
                for reward in required_rewards
            )
        ):
            await interaction.response.send_message(
                """
❌ Please set stock and a limit of 1 or more for all rewards first

Use:
/setstock <reward> <stock>
/setlimit <reward> <limit>
"""
            )

            return



        count = generate_queue(
            guild_id,
            rewards
        )



        await interaction.response.send_message(

            f"""
✅ Queue Generated

Total Queue:
{count}

Use:

/queue <number>

to view queue
"""
        )





async def setup(bot):

    await bot.add_cog(
        Admin(bot)
    )