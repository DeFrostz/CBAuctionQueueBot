"""Slash-command category dropdown shared by the admin and queue cogs."""

import discord

# Guild League and League Prize appear as one linked entry.
CATEGORY_CHOICES = [
    discord.app_commands.Choice(
        name="Guild League / League Prize",
        value="Guild League",
    ),
    discord.app_commands.Choice(
        name="Emperium Overrun",
        value="Emperium Overrun",
    ),
    discord.app_commands.Choice(
        name="Designed Auction",
        value="Designed Auction",
    ),
    discord.app_commands.Choice(name="All", value="All"),
]
