import discord

from discord.ext import commands


CATEGORY_OPTIONS = (
    (
        "Guild League / League Prize",
        "Guild League",
        "🏆",
        "Guild League and League Prize share the same queue sequence",
    ),
    (
        "Emperium Overrun",
        "Emperium Overrun",
        "⚔️",
        "View an Emperium Overrun queue",
    ),
    (
        "Designed Auction",
        "Designed Auction",
        "📂",
        "View a Designed Auction queue",
    ),
)


# Per-user selection for the shared persistent panel.
# Key: (guild_id, user_id)
# Value: (category_name, category_value)
SELECTED_CATEGORIES = {}


class QueueNumberModal(discord.ui.Modal, title="View Auction Queue"):
    queue_number = discord.ui.TextInput(
        label="Queue Number",
        placeholder="Example: 5",
        required=True,
        min_length=1,
        max_length=6,
    )

    def __init__(self, bot, category_name, category_value):
        super().__init__()
        self.bot = bot
        self.category_name = category_name
        self.category_value = category_value

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
            # /queuelist already knows that Guild League and League Prize
            # are linked. Passing Guild League here therefore queries both.
            category_choice = discord.app_commands.Choice(
                name=self.category_name,
                value=self.category_value,
            )

            await queue_cog.queuelist.callback(
                queue_cog,
                interaction,
                number,
                category_choice,
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


class QueueCategorySelect(discord.ui.Select):
    def __init__(self, bot):
        self.bot = bot

        options = [
            discord.SelectOption(
                label=label,
                value=value,
                emoji=emoji,
                description=description,
            )
            for label, value, emoji, description in CATEGORY_OPTIONS
        ]

        super().__init__(
            placeholder="1. Select auction category...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="auction_queue:category_v2",
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        selected_value = self.values[0]

        selected_name = next(
            label
            for label, value, _, _ in CATEGORY_OPTIONS
            if value == selected_value
        )

        guild_id = interaction.guild.id if interaction.guild else 0
        key = (guild_id, interaction.user.id)

        SELECTED_CATEGORIES[key] = (
            selected_name,
            selected_value,
        )

        await interaction.response.send_message(
            f"✅ Selected **{selected_name}**. Now click **View Queue**.",
            ephemeral=True,
        )


class QueuePanelView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.add_item(QueueCategorySelect(bot))

    @discord.ui.button(
        label="View Queue",
        emoji="🔎",
        style=discord.ButtonStyle.primary,
        custom_id="auction_queue:view_queue_v2",
        row=1,
    )
    async def view_queue(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        guild_id = interaction.guild.id if interaction.guild else 0
        key = (guild_id, interaction.user.id)

        selected = SELECTED_CATEGORIES.get(key)

        if selected is None:
            await interaction.response.send_message(
                "❌ Please select an auction category first.",
                ephemeral=True,
            )
            return

        category_name, category_value = selected

        await interaction.response.send_modal(
            QueueNumberModal(
                self.bot,
                category_name,
                category_value,
            )
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
                "**1.** Select the auction category below.\n"
                "**2.** Click **View Queue**.\n"
                "**3.** Enter the **Queue Number** you want to view.\n\n"
                "🏆 **Guild League / League Prize** are linked and use "
                "one shared queue sequence.\n"
                "⚔️ **Emperium Overrun** has its own queue sequence.\n"
                "📂 **Designed Auction** has its own queue sequence.\n\n"
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
    # Register the persistent component handlers so previously-posted
    # v2 panels continue working after the bot restarts.
    bot.add_view(QueuePanelView(bot))

    await bot.add_cog(
        QueuePanel(bot)
    )
