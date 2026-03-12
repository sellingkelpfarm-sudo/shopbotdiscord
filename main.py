import discord
from discord.ext import commands
import os
import sqlite3
import sys

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True # Bật thêm presence nếu cần theo dõi trạng thái

bot = commands.Bot(command_prefix="!", intents=intents)

# --- HÀM NẠP COGS ---
async def load_extensions():
    extensions = ["sell_system", "invite_system", "MenuRole"]
    for ext in extensions:
        try:
            # Nếu file nằm trong cùng thư mục, dùng ext trực tiếp
            # Nếu nằm trong thư mục cogs, hãy đổi thành f"cogs.{ext}"
            await bot.load_extension(ext)
            print(f"✅ Đã nạp thành công: {ext}")
        except Exception as e:
            print(f"❌ Lỗi khi nạp {ext}: {e}")

@bot.event
async def setup_hook():
    # Gọi hàm nạp các file hệ thống
    await load_extensions()

@bot.event
async def on_ready():
    # Thông báo trạng thái nạp dữ liệu từ Cog
    sell_mod = sys.modules.get('sell_system')
    if sell_mod and hasattr(sell_mod, 'bank_waiting'):
        count = len(sell_mod.bank_waiting)
        print(f"📦 Hệ thống bán hàng đã sẵn sàng. Đang quản lý {count} đơn hàng trong RAM.")
    
    # Cập nhật trạng thái cho Bot (Ví dụ: Đang xem Shop)
    await bot.change_presence(activity=discord.Game(name="LoTuss's Shop"))
    
    print(f"🚀 Bot đã sẵn sàng: {bot.user}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

# --- CHẠY BOT ---
# Đảm bảo bạn đã set TOKEN trong Environment Variables hoặc thay trực tiếp vào đây
TOKEN = os.getenv("TOKEN")

if TOKEN:
    try:
        bot.run(TOKEN)
    except discord.errors.LoginFailure:
        print("❌ TOKEN không hợp lệ. Vui lòng kiểm tra lại.")
    except Exception as e:
        print(f"❌ Lỗi khởi động: {e}")
else:
    print("❌ Không tìm thấy TOKEN trong môi trường (Environment Variable).")
