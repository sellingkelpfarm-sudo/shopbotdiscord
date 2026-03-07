import discord
from discord.ext import commands
import os

# ========================

# INTENTS

# ========================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# ========================

# BOT

# ========================

bot = commands.Bot(
command_prefix="!",
intents=intents
)

# ========================

# READY EVENT

# ========================

@bot.event
async def on_ready():
print(f"Bot đã đăng nhập: {bot.user}")
print("Bot đang hoạt động...")

# ========================

# LOAD COGS

# ========================

async def load_cogs():
cogs = [
"sell_system",
"MenuRole",
"card_system"
]

```
for cog in cogs:
    try:
        await bot.load_extension(cog)
        print(f"Loaded: {cog}")
    except Exception as e:
        print(f"Lỗi load {cog}: {e}")
```

# ========================

# SETUP HOOK

# ========================

async def setup_hook():
await load_cogs()

bot.setup_hook = setup_hook

# ========================

# TOKEN

# ========================

TOKEN = os.getenv("TOKEN")

if TOKEN is None:
print("Không tìm thấy TOKEN trong Railway variables")
else:
bot.run(TOKEN)

