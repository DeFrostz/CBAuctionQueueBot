import discord
from discord.ext import commands

from config import TOKEN


intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


@bot.event
async def on_ready():
    print(f"Bot Online : {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")

    except Exception as e:
        print(e)


async def load_extensions():

    await bot.load_extension(
        "cogs.admin"
    )

    await bot.load_extension(
        "cogs.queue"
    )


async def main():

    async with bot:

        await load_extensions()

        await bot.start(TOKEN)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())