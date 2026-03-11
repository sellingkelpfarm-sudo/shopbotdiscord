import discord
from discord.ext import commands, tasks
import random
import string
import time
import asyncio
import sqlite3
import os
from datetime import datetime, timedelta

# ======================
# CONFIGURATION
# ======================
BANK_CHANNEL_ID = 1479440469120389221
PAYMENT_LOG_CHANNEL_ID = 1481239066115571885 # Kênh thông báo lịch sử
PAID_ROLE_ID = 1479550698982215852           # Role bảo hành
FEEDBACK_CHANNEL_ID = 1481245879607492769    # ID kênh đánh giá dịch vụ
ORDER_TIMEOUT = 900

cooldowns = {}
buy_cooldowns = {}
bank_waiting = {}
order_activity = {}
user_orders = {}

# ======================
# DATABASE SYSTEM
# ======================
def init_db():
    conn = sqlite3.connect('bank_orders.db')
    c = conn.cursor()
    # Lưu các đơn đang chờ thanh toán
    c.execute('''CREATE TABLE IF NOT EXISTS waiting_orders 
                 (code TEXT PRIMARY KEY, channel_id INTEGER, product TEXT, link TEXT, 
                  price INTEGER, user_id INTEGER)''')
    # Lưu thông tin bảo hành
    c.execute('''CREATE TABLE IF NOT EXISTS warranty_users 
                 (user_id INTEGER, guild_id INTEGER, expiry_timestamp REAL)''')
    conn.commit()
    conn.close()

def db_save_waiting(code, channel_id, product, link, price, user_id):
    conn = sqlite3.connect('bank_orders.db')
    conn.execute("INSERT OR REPLACE INTO waiting_orders VALUES (?, ?, ?, ?, ?, ?)",
                 (code, channel_id, product, link, price, user_id))
    conn.commit()
    conn.close()

def db_load_waiting():
    global bank_waiting
    conn = sqlite3.connect('bank_orders.db')
    c = conn.cursor()
    c.execute("SELECT * FROM waiting_orders")
    rows = c.fetchall()
    for r in rows:
        bank_waiting[r[0]] = {"channel": r[1], "product": r[2], "link": r[3], "price": r[4], "user": r[5]}
    conn.close()

def db_delete_waiting(code):
    conn = sqlite3.connect('bank_orders.db')
    conn.execute("DELETE FROM waiting_orders WHERE code = ?", (code,))
    conn.commit()
    conn.close()

init_db()
db_load_waiting()

# ======================
# UTILS
# ======================
def generate_code():
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if code not in bank_waiting:
            return code

def anti_spam(user_id):
    now = time.time()
    if user_id in cooldowns and now - cooldowns[user_id] < 10: return False
    cooldowns[user_id] = now
    return True

def anti_spam_buy(user_id):
    now = time.time()
    if user_id in buy_cooldowns and now - buy_cooldowns[user_id] < 10: return False
    buy_cooldowns[user_id] = now
    return True

# ======================
# WARRANTY TASK (Xóa Role sau 3 ngày)
# ======================
@tasks.loop(hours=1)
async def check_warranty_task():
    now = datetime.now().timestamp()
    conn = sqlite3.connect('bank_orders.db')
    c = conn.cursor()
    c.execute("SELECT user_id, guild_id FROM warranty_users WHERE expiry_timestamp <= ?", (now,))
    expired = c.fetchall()
    
    for u_id, g_id in expired:
        guild = bot.get_guild(g_id)
        if guild:
            member = guild.get_member(u_id)
            role = guild.get_role(PAID_ROLE_ID)
            if member and role:
                try: await member.remove_roles(role)
                except: pass
    
    c.execute("DELETE FROM warranty_users WHERE expiry_timestamp <= ?", (now,))
    conn.commit()
    conn.close()

# ======================
# VIEWS & LOGIC
# ======================

async def auto_close_channel(channel, order_code, user_id):
    await asyncio.sleep(ORDER_TIMEOUT)
    if order_code not in order_activity or order_activity[order_code]: return
    try:
        await channel.send("⌛ Đơn hàng đã bị đóng do không thanh toán trong 15 phút.")
        await asyncio.sleep(5)
        await channel.delete()
    except: pass
    if order_code in bank_waiting: db_delete_waiting(order_code); del bank_waiting[order_code]
    if user_id in user_orders:
        user_orders[user_id] = max(0, user_orders[user_id] - 1)

class CancelConfirm(discord.ui.View):
    @discord.ui.button(label="✅ CÓ", style=discord.ButtonStyle.red)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        await interaction.response.send_message("⏳ Kênh sẽ bị xoá sau 5 giây.")
        await asyncio.sleep(5)
        try: await interaction.channel.delete()
        except: pass
        if user_id in user_orders: user_orders[user_id] = max(0, user_orders[user_id] - 1)

    @discord.ui.button(label="❌ KHÔNG", style=discord.ButtonStyle.green)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("👍 Đơn hàng vẫn được giữ.", ephemeral=True)

async def bank_countdown(message, order_code):
    seconds = 300
    while seconds > 0:
        if order_code not in bank_waiting: return
        m, s = divmod(seconds, 60)
        embed = message.embeds[0]
        embed.set_footer(text=f"⏳ Thời gian còn lại: {m:02}:{s:02}")
        try: await message.edit(embed=embed)
        except: break
        await asyncio.sleep(1)
        seconds -= 1
    if order_code in bank_waiting:
        db_delete_waiting(order_code)
        del bank_waiting[order_code]
        embed = discord.Embed(title="❌ QUÁ THỜI GIAN CHUYỂN KHOẢN", description="Vui lòng tạo lại đơn!", color=discord.Color.red())
        try: await message.edit(embed=embed, view=None)
        except: pass

class PaymentView(discord.ui.View):
    def __init__(self, bank_price, product, link, order_code):
        super().__init__(timeout=None)
        self.bank_price, self.product, self.link, self.code = bank_price, product, link, order_code

    @discord.ui.button(label="💳 CHUYỂN KHOẢN", style=discord.ButtonStyle.green)
    async def bank(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not anti_spam(interaction.user.id):
            await interaction.response.send_message("⏳ Bạn thao tác quá nhanh.", ephemeral=True)
            return
        order_activity[self.code] = True
        qr = f"https://img.vietqr.io/image/MB-0764495919-compact2.png?amount={self.bank_price}&addInfo={self.code}"
        embed = discord.Embed(
            title="💳 THANH TOÁN CHUYỂN KHOẢN",
            description=(f"📦 **Sản phẩm:** {self.product}\n💰 **Số tiền:** {self.bank_price:,} VND\n"
                         f"🧾 **Mã đơn:** {self.code}\n📥 **Nội dung CK:** `{self.code}`\n\n"
                         f"#lưu ý: nội dung chuyển khoản không được chỉnh sửa!\nVui lòng chụp bill lên đây nếu gặp lỗi!"),
            color=discord.Color.green()
        )
        embed.set_image(url=qr)
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        bank_waiting[self.code] = {"channel": interaction.channel.id, "link": self.link, "product": self.product, "price": self.bank_price, "user": interaction.user.id}
        db_save_waiting(self.code, interaction.channel.id, self.product, self.link, self.bank_price, interaction.user.id)
        asyncio.create_task(bank_countdown(msg, self.code))

    @discord.ui.button(label="❌ HỦY ĐƠN", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="⚠ XÁC NHẬN HỦY ĐƠN", description="BẠN CÓ CHẮC HỦY ĐƠN HÀNG CHỨ?", color=discord.Color.orange())
        await interaction.response.send_message(embed=embed, view=CancelConfirm())

class BuyView(discord.ui.View):
    def __init__(self, bank_price, product, link):
        super().__init__(timeout=None)
        self.bank_price, self.product, self.link = bank_price, product, link

    @discord.ui.button(label="🛒 MUA NGAY", style=discord.ButtonStyle.green)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        if not anti_spam_buy(user_id):
            await interaction.response.send_message("⏳ Bạn đang tạo đơn quá nhanh.", ephemeral=True)
            return
        if user_orders.get(user_id, 0) >= 3:
            await interaction.response.send_message("🚫 Bạn đã đạt giới hạn 3 đơn hàng đang mở.", ephemeral=True)
            return
        
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="orders") or await guild.create_category("orders")
        order_code = generate_code()
        channel = await guild.create_text_channel(name=f"{order_code}-{interaction.user.name}", category=category)
        await channel.set_permissions(guild.default_role, view_channel=False)
        await channel.set_permissions(interaction.user, view_channel=True, send_messages=True)
        
        user_orders[user_id] = user_orders.get(user_id, 0) + 1
        embed = discord.Embed(title="# 💳 XÁC NHẬN THANH TOÁN BẰNG NGÂN HÀNG", 
                              description=f"📦 **Tên hàng:** {self.product}\n💰 **Số tiền:** {self.bank_price:,} VND\n🆔 **Mã đơn:** {order_code}\n\n👇 Chọn phương thức thanh toán",
                              color=discord.Color.blue())
        await channel.send(interaction.user.mention, embed=embed, view=PaymentView(self.bank_price, self.product, self.link, order_code))
        order_activity[order_code] = False
        asyncio.create_task(auto_close_channel(channel, order_code, user_id))
        await interaction.response.send_message(f"✅ Đơn hàng đã tạo: {channel.mention}", ephemeral=True)

class SellSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="sellbank")
    async def sellbank(self, ctx, bank_price: int, link: str):
        product = ctx.channel.name
        embed = discord.Embed(title="🛒 THANH TOÁN BẰNG CÁCH CHUYỂN KHOẢN NGÂN HÀNG", 
                              description=f"📦 **Tên hàng:** {product}\n\n💳 **Số tiền**: {bank_price:,} VND\n\n👇 **Nhấn nút MUA NGAY bên dưới để bắt đầu thanh toán**",
                              color=discord.Color.blue())
        await ctx.send(embed=embed, view=BuyView(bank_price, product, link))

    @commands.command(name="dabank")
    @commands.has_permissions(administrator=True)
    async def dabank(self, ctx, order_code: str):
        order_code = order_code.upper()
        if order_code not in bank_waiting:
            await ctx.send("❌ Không tìm thấy mã đơn này.")
            return

        data = bank_waiting[order_code]
        user_id = data["user"]
        guild = ctx.guild
        member = guild.get_member(user_id)

        # 1. Thông báo tại Ticket
        channel = self.bot.get_channel(data["channel"])
        embed_success = discord.Embed(title="🎉 THANH TOÁN THÀNH CÔNG (ADMIN)", description="Admin đã xác nhận giao dịch!", color=discord.Color.green())
        embed_success.add_field(name="📦 Tên hàng", value=data["product"], inline=False)
        embed_success.add_field(name="💰 Số tiền", value=f"{data['price']:,} VND")
        embed_success.add_field(name="📥 Link tải", value=data["link"], inline=False)
        if channel: await channel.send(embed=embed_success)

        # 2. Thông báo Lịch sử (Public)
        log_channel = self.bot.get_channel(PAYMENT_LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(f"<@{user_id}> đã thanh toán đơn hàng **{data['product']}** với số tiền **{data['price']:,} VND**, Bạn đánh giá dịch vụ của chúng tớ tại <#{FEEDBACK_CHANNEL_ID}> nhé!")

        # 3. Cấp Role bảo hành & Lưu DB
        if member:
            role = guild.get_role(PAID_ROLE_ID)
            if role:
                await member.add_roles(role)
                expiry = (datetime.now() + timedelta(days=3)).timestamp()
                conn = sqlite3.connect('bank_orders.db')
                conn.execute("INSERT INTO warranty_users VALUES (?, ?, ?)", (user_id, guild.id, expiry))
                conn.commit()
                conn.close()

            # 4. Gửi DMs cho khách
            dm_msg = (f"Chúc mừng bạn đã mua thành công đơn hàng **{data['product']}** với số tiền **{data['price']:,} VND**. "
                      f"Bạn có 3 ngày bảo hành từ LoTuss's Schematic Shop, sau 3 ngày bảo hành sẽ hết hạn! "
                      f"Cảm ơn bạn đã tin tưởng và sử dụng dịch vụ của chúng tôi nhé!")
            try: await member.send(dm_msg)
            except: pass

        db_delete_waiting(order_code)
        del bank_waiting[order_code]
        if user_id in user_orders: user_orders[user_id] = max(0, user_orders[user_id] - 1)
        await ctx.send(f"✅ Đã xác nhận đơn `{order_code}` thành công.")

# Khởi tạo Bot để chạy task (Phần này bạn để trong file main chính của bạn)
# bot = commands.Bot(...)
# bot.add_cog(SellSystem(bot))
# check_warranty_task.start()
