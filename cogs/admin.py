import discord

from discord.ext import commands

from database import (
    save_reward,
    get_rewards
)

from generator import (
    generate_queue
)


class Admin(commands.Cog):

    def __init__(self, bot):

        self.bot = bot



    # -----------------------------
    # /reward
    # -----------------------------

    @discord.app_commands.command(
        name="reward",
        description="Set reward stock"
    )
    @discord.app_commands.describe(
        reward="CARD / FEATHER_S / FEATHER_A",
        stock="Amount of reward",
        limit="Limit per queue"
    )
    async def reward(
        self,
        interaction: discord.Interaction,

        reward: str,

        stock: int,

        limit: int

    ):


        guild_id = str(
            interaction.guild.id
        )


        reward = reward.upper()



        if reward not in [
            "CARD",
            "FEATHER_S",
            "FEATHER_A"
        ]:

            await interaction.response.send_message(
                "❌ Reward type incorrect"
            )

            return



        save_reward(
            guild_id,
            reward,
            stock,
            limit
        )



        await interaction.response.send_message(
            f"""
✅ Reward Updated

🎁 {reward}

Stock:
{stock}

Limit / Queue:
{limit}
"""
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


        guild_id = str(
            interaction.guild.id
        )


        rewards = get_rewards(
            guild_id
        )


        if len(rewards) < 3:


            await interaction.response.send_message(
                """
❌ Please setup all rewards first

CARD
FEATHER_S
FEATHER_A
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