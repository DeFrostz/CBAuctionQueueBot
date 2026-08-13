import discord

from discord.ext import commands


class QueueNumberModal(discord.ui.Modal, title="View Auction Queue"):
    queue_number = discord.ui.TextInput(
        label="Queue Number",
        placeholder="Example: 5",
        required=True,
        min_length=1,
        max_length=6,
    )

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        try:
            number = int(self.queue_number.value.strip())

            if number < 1:
                raise ValueError

        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter a valid queue number greater than 0.",
                ephemeral=True,
            )
            return

        queue_cog = self.bot.get_cog("Queue")

        if queue_cog is None:
            await interaction.response.send_message(
                "❌ Queue service is currently unavailable.",
                ephemeral=True,
            )
            return

        try:
            # Reuse the exact same logic as:
            # /queuelist number:<number>
            await queue_cog.queuelist.callback(
                queue_cog,
                interaction,
                number,
                None,
            )

        except Exception as error:
            print(f"Queue panel lookup error: {error}")

            message = "❌ Failed to load that queue. Please try again."

            if interaction.response.is_done():
                await interaction.followup.send(
                    message,
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    message,
                    ephemeral=True,
                )


class QueuePanelView(discord.ui.View):
    def __init__(self, bot):
        # timeout=None + a fixed custom_id makes this a persistent view.
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="View Queue",
        emoji="🔎",
        style=discord.ButtonStyle.primary,
        custom_id="auction_queue:view_queue",
    )
    async def view_queue(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await interaction.response.send_modal(
            QueueNumberModal(self.bot)
        )


class QueuePanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(
        name="queuepanel",
        description="Post the auction queue lookup panel",
    )
    async def queuepanel(
        self,
        interaction: discord.Interaction,
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used in a server.",
                ephemeral=True,
            )
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need Administrator permission to post the queue panel.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="📋 Auction Queue",
            description=(
                "Press **View Queue** and enter the queue number "
                "you want to check.\n\n"
                "The queue result will only be visible to you."
            ),
        )

        embed.set_footer(
            text="Auction Queue Lookup"
        )

        await interaction.response.send_message(
            embed=embed,
            view=QueuePanelView(self.bot),
        )


async def setup(bot):
    # Register the persistent button handler so previously-posted panels
    # continue working after the bot restarts.
    bot.add_view(QueuePanelView(bot))

    await bot.add_cog(
        QueuePanel(bot)
    )
