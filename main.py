import discord
from discord.ext import commands
import os

from MenuRole import setup_menu
from sell_system import setup_sell

token = "token"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot đã online: {bot.user}")

# Load hệ thống
setup_menu(bot)
setup_sell(bot)

bot.run(os.getenv("token"))

