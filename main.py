import discord
from discord.ext import commands
import os
import sqlite3
import sys

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- HÀM NẠP COGS ---
async def load_extensions():
    extensions = ["sell_system", "invite_system", "MenuRole"]
    for ext in extensions:
        try:
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
    # Khôi phục dữ liệu đơn hàng từ Database vào RAM của sell_system
    # Kiểm tra xem sell_system đã được nạp vào sys.modules chưa
    sell_mod = sys.modules.get('sell_system')
    if sell_mod:
        try:
            conn = sqlite3.connect('bank_orders.db')
            c = conn.cursor()
            # Đảm bảo bảng tồn tại trước khi lấy dữ liệu
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='waiting_orders'")
            if c.fetchone():
                c.execute("SELECT code, channel_id, product, link, price, user_id FROM waiting_orders")
                rows = c.fetchall()
                for row in rows:
                    sell_mod.bank_waiting[row[0]] = {
                        "channel": row[1], "product": row[2], 
                        "link": row[3], "price": row[4], "user": row[5]
                    }
                print(f"📦 Đã khôi phục {len(rows)} đơn hàng vào RAM.")
            conn.close()
        except Exception as e:
            print(f"⚠️ Lỗi khôi phục đơn hàng: {e}")
    
    print(f"🚀 Bot đã sẵn sàng: {bot.user}")

# --- CHẠY BOT ---
TOKEN = os.getenv("TOKEN")
if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ Không tìm thấy TOKEN trong môi trường (Environment Variable).")
    
