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


async def sync_guild_commands(guild):
    bot.tree.copy_global_to(guild=guild)
    synced = await bot.tree.sync(guild=guild)
    print(f"Synced {len(synced)} commands to {guild.name} ({guild.id})")


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