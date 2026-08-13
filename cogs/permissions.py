import discord

from discord import app_commands
from discord.ext import commands


ADMIN_ONLY_COMMANDS = {
    "setallstock",
    "setalllimit",
    "clearqueues",
    "generate",
    "clearconfig",
    "extra",
    "queuepanel",
}


def is_administrator(interaction: discord.Interaction) -> bool:
    return (
        interaction.guild is not None
        and isinstance(interaction.user, discord.Member)
        and interaction.user.guild_permissions.administrator
    )


async def send_permission_error(
    interaction: discord.Interaction,
    message: str,
):
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


async def admin_only_check(interaction: discord.Interaction) -> bool:
    if is_administrator(interaction):
        return True

    await send_permission_error(
        interaction,
        "❌ This command is reserved for server administrators.",
    )
    return False


def interaction_has_queue_number(interaction: discord.Interaction) -> bool:
    """
    /queuelist is special:

    - /queuelist number:<n>                  -> everyone
    - /queuelist number:<n> category:<cat>  -> everyone
    - /queuelist                            -> admin only
    - /queuelist category:<cat>             -> admin only

    The Queue Panel calls the queue callback directly, so normal users
    can still use the panel without being affected by this slash-command check.
    """
    data = interaction.data or {}
    options = data.get("options", [])

    return any(
        option.get("name") == "number"
        and option.get("value") is not None
        for option in options
    )


async def queuelist_check(interaction: discord.Interaction) -> bool:
    if is_administrator(interaction):
        return True

    if interaction_has_queue_number(interaction):
        return True

    await send_permission_error(
        interaction,
        "❌ Administrator permission is required to view the full queue list. "
        "Use `/queuelist number:<queue>` or the Queue Panel to view one queue.",
    )
    return False


async def global_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
):
    # Permission checks above already send their own ephemeral reply.
    if isinstance(error, app_commands.CheckFailure):
        if interaction.response.is_done():
            return

        await interaction.response.send_message(
            "❌ You do not have permission to use this command.",
            ephemeral=True,
        )
        return

    # Keep unexpected command errors private as well.
    print(f"Application command error: {error}")

    message = "❌ An unexpected error occurred while running this command."

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


class Permissions(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._admin_commands = []
        self._queuelist_command = None

    async def cog_load(self):
        # This extension is loaded after the command cogs, so their app
        # commands already exist in the tree and can receive checks here.
        for command_name in ADMIN_ONLY_COMMANDS:
            command = self.bot.tree.get_command(command_name)

            if command is None:
                print(
                    f"Permission setup warning: /{command_name} was not found"
                )
                continue

            command.add_check(admin_only_check)
            self._admin_commands.append(command)

        queuelist = self.bot.tree.get_command("queuelist")

        if queuelist is None:
            print("Permission setup warning: /queuelist was not found")
        else:
            queuelist.add_check(queuelist_check)
            self._queuelist_command = queuelist

        # Central app-command error handler: all uncaught errors are ephemeral.
        self.bot.tree.error(global_app_command_error)

    async def cog_unload(self):
        # Prevent duplicated checks if this extension is reloaded.
        for command in self._admin_commands:
            command.remove_check(admin_only_check)

        if self._queuelist_command is not None:
            self._queuelist_command.remove_check(queuelist_check)


async def setup(bot):
    await bot.add_cog(
        Permissions(bot)
    )
