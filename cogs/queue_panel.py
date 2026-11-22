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


class QueuePanelView(discord.ui.View):
    """One button per category. Nothing is remembered between clicks, so the
    panel keeps working after the bot restarts."""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    async def open_modal(self, interaction: discord.Interaction, index: int):
        label, value, _, _ = CATEGORY_OPTIONS[index]
        await interaction.response.send_modal(
            QueueNumberModal(self.bot, label, value)
        )

    @discord.ui.button(
        label="Guild League / League Prize",
        emoji="🏆",
        style=discord.ButtonStyle.primary,
        custom_id="auction_queue:view_gl_lp_v3",
        row=0,
    )
    async def view_gl_lp(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.open_modal(interaction, 0)

    @discord.ui.button(
        label="Emperium Overrun",
        emoji="⚔️",
        style=discord.ButtonStyle.primary,
        custom_id="auction_queue:view_emperium_v3",
        row=1,
    )
    async def view_emperium(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.open_modal(interaction, 1)

    @discord.ui.button(
        label="Designed Auction",
        emoji="📂",
        style=discord.ButtonStyle.primary,
        custom_id="auction_queue:view_designed_v3",
        row=1,
    )
    async def view_designed(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.open_modal(interaction, 2)


class LegacyQueuePanelView(discord.ui.View):
    """Old v2 panels (dropdown + View Queue button) still exist in servers.
    Answer them with instructions instead of "interaction failed"."""

    def __init__(self):
        super().__init__(timeout=None)

    async def _notice(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "ℹ️ This panel is outdated. Ask an admin to post a new one with `/queuepanel`.",
            ephemeral=True,
        )

    @discord.ui.select(
        placeholder="1. Select auction category...",
        options=[discord.SelectOption(label="Outdated panel", value="legacy")],
        custom_id="auction_queue:category_v2",
        row=0,
    )
    async def legacy_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        await self._notice(interaction)

    @discord.ui.button(
        label="View Queue",
        emoji="🔎",
        style=discord.ButtonStyle.primary,
        custom_id="auction_queue:view_queue_v2",
        row=1,
    )
    async def legacy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._notice(interaction)


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

        embed = discord.Embed(
            title="📋 Auction Queue",
            description=(
                "**1.** Click the button for the auction category.\n"
                "**2.** Enter the **Queue Number** you want to view.\n\n"
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
    # Persistent component handlers survive bot restarts.
    bot.add_view(QueuePanelView(bot))
    bot.add_view(LegacyQueuePanelView())

    await bot.add_cog(
        QueuePanel(bot)
    )
