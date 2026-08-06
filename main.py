import discord
from discord.ext import commands

from config import TOKEN


intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

commands_synced = False


@bot.event
async def on_ready():
    global commands_synced

    print(f"Bot Online : {bot.user}")

    if commands_synced:
        return

    if not bot.guilds:
        print("No Discord servers found for this bot")
        return

    for guild in bot.guilds:
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"Synced {len(synced)} commands to {guild.name} ({guild.id})")

    commands_synced = True


async def load_extensions():
    await bot.load_extension("cogs.admin")
    await bot.load_extension("cogs.queue")


async def main():

    async with bot:

        await load_extensions()

        await bot.start(TOKEN)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())