import discord
from discord.ext import commands
import asyncio
import os

TOKEN = os.getenv("TOKEN")  # Railway sẽ lấy token từ Variables

intents = discord.Intents.all()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


@bot.event
async def on_ready():
    print(f"✅ Bot online: {bot.user}")


async def load_extensions():
    await bot.load_extension("sell_system")


async def main():
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)


asyncio.run(main())
