import discord

from discord.ext import commands

from database import (
    get_queue,
    get_queue_count,
    get_rewards
)


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

                slot_text = (
                    f"{slots[0]}-{slots[-1]}"
                )


            result.append(
                f"Page {page} : Slot {slot_text}"
            )


        return "\n".join(result)

    @discord.app_commands.command(
        name="extra",
        description="View rewards that are not assigned to a queue"
    )
    async def extra(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used in a server"
            )
            return

        guild_id = str(interaction.guild.id)
        rewards = {
            row["reward_type"]: row
            for row in get_rewards(guild_id)
        }
        queue_count = get_queue_count(guild_id)
        reward_order = ("CARD", "FEATHER_S", "FEATHER_A")
        reward_names = {
            "CARD": "🃏 Card",
            "FEATHER_S": "🌗 Light-Dark",
            "FEATHER_A": "⏳ Time-Space"
        }

        embed = discord.Embed(
            title="📦 Extra Rewards",
            description=(
                f"Rewards not assigned to the current {queue_count} queue(s)"
            )
        )

        for reward in reward_order:
            row = rewards.get(reward)
            if row is None:
                value = "Not configured"
            else:
                assigned = queue_count * row["limit_per_queue"]
                extra = max(row["stock"] - assigned, 0)
                value = (
                    f"Stock: {row['stock']}\n"
                    f"In queues: {assigned}\n"
                    f"Extra: **{extra}**"
                )

            embed.add_field(
                name=reward_names[reward],
                value=value,
                inline=False
            )

        await interaction.response.send_message(embed=embed)




    @discord.app_commands.command(

        name="queue",

        description="View your auction queue"

    )
    @discord.app_commands.describe(

        number="Queue number"

    )
    async def queue(

        self,

        interaction: discord.Interaction,

        number: int

    ):


        guild_id = str(
            interaction.guild.id
        )


        data = get_queue(
            guild_id,
            number
        )


        if not data:


            await interaction.response.send_message(

                "❌ Queue not found"

            )

            return



        reward_group = {}


        for row in data:


            reward = row["reward_type"]


            if reward not in reward_group:

                reward_group[reward] = []



            reward_group[reward].append(
                row
            )



        embed = discord.Embed(

            title=f"📋 Queue #{number}",

            description="Auction Position"

        )


        name_map = {

            "CARD":
                "🃏 Card",

            "FEATHER_S":
                "🌗 Light-Dark",

            "FEATHER_A":
                "⏳ Time-Space"

        }



        for reward, rows in reward_group.items():


            text = self.group_slots(
                rows
            )


            embed.add_field(

                name=name_map.get(
                    reward,
                    reward
                ),

                value=text,

                inline=False

            )



        await interaction.response.send_message(

            embed=embed

        )





async def setup(bot):

    await bot.add_cog(
        Queue(bot)
    )