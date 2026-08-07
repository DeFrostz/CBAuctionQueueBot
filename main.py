import os
import discord
from discord.ext import commands

from config import TOKEN
from database import init_database


intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

commands_synced = False

# Support either a single SYNC_GUILD_ID or multiple as comma-separated SYNC_GUILD_IDS
SYNC_GUILD_ID = os.environ.get("SYNC_GUILD_ID")
SYNC_GUILD_IDS = os.environ.get("SYNC_GUILD_IDS")


async def sync_guild_commands(guild):
    bot.tree.copy_global_to(guild=guild)
    synced = await bot.tree.sync(guild=guild)
    print(f"Synced {len(synced)} commands to {getattr(guild, 'name', guild)} ({getattr(guild, 'id', guild)})")


async def sync_to_guild_id(guild_id_str: str):
    """Force a guild-scoped sync using an ID string from env var. Useful for dev/testing so commands appear immediately."""
    try:
        gid = int(guild_id_str)
    except Exception as e:
        print(f"SYNC_GUILD_ID is invalid: {e}")
        return
    # Create a lightweight Guild-like object for logging (we may not have the full Guild until the bot is in it)
    obj = discord.Object(id=gid)
    try:
        bot.tree.copy_global_to(guild=obj)
        synced = await bot.tree.sync(guild=obj)
        print(f"Synced {len(synced)} commands to guild id {gid}")
    except Exception as e:
        print(f"Failed to sync commands to guild id {gid}: {e}")


async def sync_to_guild_ids(guild_ids_str: str):
    """Accepts a comma-separated list of guild IDs and attempts to sync each."""
    ids = [s.strip() for s in guild_ids_str.split(",") if s.strip()]
    for gid_str in ids:
        await sync_to_guild_id(gid_str)


@bot.event
async def on_ready():
    global commands_synced

    print(f"Bot Online : {bot.user}")
    print(
        f"Connected to {len(bot.guilds)} server(s): "
        f"{', '.join(guild.name for guild in bot.guilds) or 'none'}"
    )

    if commands_synced:
        return

    # If a specific SYNC_GUILD_ID or SYNC_GUILD_IDS is set, force a sync to that guild(s) for immediate testing
    if SYNC_GUILD_IDS:
        await sync_to_guild_ids(SYNC_GUILD_IDS)
        commands_synced = True
        return

    if SYNC_GUILD_ID:
        await sync_to_guild_id(SYNC_GUILD_ID)
        commands_synced = True
        return

    if not bot.guilds:
        print("No Discord servers found for this bot")
        return

    for guild in bot.guilds:
        await sync_guild_commands(guild)

    commands_synced = True


@bot.event
async def on_guild_join(guild):
    await sync_guild_commands(guild)


async def load_extensions():
    await bot.load_extension("cogs.admin")
    await bot.load_extension("cogs.queue")


async def main():

    init_database()

    async with bot:

        await load_extensions()

        await bot.start(TOKEN)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
