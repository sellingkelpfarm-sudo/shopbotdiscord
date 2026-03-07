import discord
from discord.ext import commands
import os

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


@bot.event
async def on_ready():
    print(f"Bot đã đăng nhập: {bot.user}")
    print("Bot đang hoạt động...")


async def load_cogs():
    await bot.load_extension("sell_system")
    await bot.load_extension("MenuRole")
    await bot.load_extension("card_system")


async def setup_hook():
    await load_cogs()


bot.setup_hook = setup_hook


TOKEN = os.getenv("TOKEN")  # Railway đọc token từ biến môi trường

bot.run(TOKEN)
