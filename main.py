import discord
from discord.ext import commands
import os

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot đã đăng nhập: {bot.user}")

@bot.event
async def setup_hook():
    await bot.load_extension("sell_system")
    await bot.load_extension("MenuRole")
    await bot.load_extension("card_system")

TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
