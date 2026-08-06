import discord

from discord.ext import commands

from database import get_queue


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