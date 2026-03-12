import discord
from discord.ext import commands, tasks
import random
import string
import time
import asyncio
import sqlite3
import os
from datetime import datetime, timedelta

# ===== CẤU HÌNH ID =====
BANK_CHANNEL_ID = 1479440469120389221
PAYMENT_LOG_CHANNEL_ID = 1481239066115571885
PAID_ROLE_ID = 1479550698982215852
FEEDBACK_CHANNEL_MENTION = "<#1481245879607492769>" 
ORDER_TIMEOUT = 900

cooldowns = {}
buy_cooldowns = {}
bank_waiting = {}
order_activity = {}
user_orders = {}
voucher_attempts = {}

# ===== DATABASE LOGIC =====
def init_db():
    conn = sqlite3.connect('bank_orders.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS waiting_orders 
                 (code TEXT PRIMARY KEY, channel_id INTEGER, product TEXT, link TEXT, 
                  price INTEGER, user_id INTEGER)''')
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

def db_delete_waiting(code):
    conn = sqlite3.connect('bank_orders.db')
    conn.execute("DELETE FROM waiting_orders WHERE code = ?", (code,))
    conn.commit()
    conn.close()

def db_load_waiting():
    global bank_waiting
    conn = sqlite3.connect('bank_orders.db')
    c = conn.cursor()
    c.execute("SELECT * FROM waiting_orders")
    rows = c.fetchall()
    for row in rows:
        bank_waiting[row[0]] = {
            "channel": row[1], "product": row[2], 
            "link": row[3], "price": row[4], "user": row[5]
        }
    conn.close()

init_db()
db_load_waiting()

def generate_code():
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if code not in bank_waiting:
            return code

def anti_spam(user_id):
    now = time.time()
    if user_id in cooldowns:
        if now - cooldowns[user_id] < 10: return False
    cooldowns[user_id] = now
    return True

def anti_spam_buy(user_id):
    now = time.time()
    if user_id in buy_cooldowns:
        if now - buy_cooldowns[user_id] < 10: return False
    buy_cooldowns[user_id] = now
    return True

# --- MODAL NHẬP VOUCHER ---
class VoucherModal(discord.ui.Modal, title='🎫 NHẬP MÃ GIẢM GIÁ'):
    voucher_input = discord.ui.TextInput(
        label='Mã Voucher',
        placeholder='Nhập mã của bạn tại đây...',
        min_length=3,
        max_length=20,
        required=True
    )

    def __init__(self, bot, order_code):
        super().__init__()
        self.bot = bot
        self.order_code = order_code

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        if voucher_attempts.get(user_id, 0) >= 3:
            return await interaction.response.send_message("🚫 Bạn đã nhập sai quá 3 lần. Chức năng voucher đã bị khóa cho đơn này!", ephemeral=True)

        invite_cog = self.bot.get_cog("InviteSystem")
        if invite_cog:
            percent, new_price = await invite_cog.process_voucher_logic(interaction, self.voucher_input.value, self.order_code)
            if percent is None:
                voucher_attempts[user_id] = voucher_attempts.get(user_id, 0) + 1
                remain = 3 - voucher_attempts[user_id]
                msg = f"❌ Mã không chính xác! Bạn còn {remain} lần thử." if remain > 0 else "🚫 Bạn đã hết lượt thử voucher!"
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                voucher_attempts[user_id] = 0
                await interaction.response.send_message(f"✅ Đã áp dụng mã thành công! Giảm **{percent}%**. Giá mới: **{new_price:,} VND**. Vui lòng nhấn lại nút **CHUYỂN KHOẢN** để nhận mã QR mới.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Hệ thống Voucher đang gặp sự cố.", ephemeral=True)

@tasks.loop(hours=1)
async def check_warranty_task(bot):
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

async def auto_close_channel(channel, order_code, user_id):
    await asyncio.sleep(ORDER_TIMEOUT)
    if order_code not in order_activity: return
    if order_activity[order_code]: return
    try:
        await channel.send("⌛ Đơn hàng đã bị đóng do không thanh toán trong 15 phút.")
        await asyncio.sleep(5)
        await channel.delete()
    except: pass
    if order_code in bank_waiting: 
        db_delete_waiting(order_code)
        del bank_waiting[order_code]
    if user_id in user_orders:
        user_orders[user_id] -= 1
        if user_orders[user_id] <= 0: del user_orders[user_id]

class CancelConfirm(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=30)
        self.user_id = user_id

    @discord.ui.button(label="✅ CÓ", style=discord.ButtonStyle.red)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⏳ Kênh sẽ bị xoá sau 5 giây.")
        await asyncio.sleep(5)
        try: await interaction.channel.delete()
        except: pass
        if self.user_id in user_orders:
            user_orders[self.user_id] -= 1
            if user_orders[self.user_id] <= 0: del user_orders[self.user_id]

    @discord.ui.button(label="❌ KHÔNG", style=discord.ButtonStyle.green)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("👍 Đơn hàng vẫn được giữ.", ephemeral=True)

async def bank_countdown(message, order_code):
    seconds = 300
    while seconds > 0:
        if order_code not in bank_waiting: return
        m = seconds // 60
        s = seconds % 60
        try:
            if message.embeds:
                embed = message.embeds[0]
                embed.set_footer(text=f"⏳ Thời gian còn lại: {m:02}:{s:02}")
                await message.edit(embed=embed)
        except: break 
        await asyncio.sleep(1)
        seconds -= 1
    if order_code in bank_waiting:
        db_delete_waiting(order_code)
        del bank_waiting[order_code]
        try:
            embed = discord.Embed(title="❌ QUÁ THỜI GIAN CHUYỂN KHOẢN", description="Vui lòng tạo lại đơn!", color=discord.Color.red())
            await message.edit(embed=embed, view=None)
        except: pass

class PaymentView(discord.ui.View):
    def __init__(self, bot, bank_price, product, link, order_code):
        super().__init__(timeout=None)
        self.bot, self.bank_price, self.product, self.link, self.code = bot, bank_price, product, link, order_code

    @discord.ui.button(label="💳 CHUYỂN KHOẢN", style=discord.ButtonStyle.green)
    async def bank(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not anti_spam(interaction.user.id):
            await interaction.response.send_message("⏳ Bạn thao tác quá nhanh.", ephemeral=True)
            return
        
        # Cập nhật lại giá từ bank_waiting trong trường hợp đã áp mã voucher
        current_price = bank_waiting[self.code]['price'] if self.code in bank_waiting else self.bank_price
        
        order_activity[self.code] = True
        qr = f"https://img.vietqr.io/image/MB-0764495919-compact2.png?amount={current_price}&addInfo={self.code}"
        embed = discord.Embed(
            title="💳 THANH TOÁN CHUYỂN KHOẢN",
            description=(
                f"📦 **Sản phẩm:** {self.product}\n"
                f"💰 **Số tiền:** {current_price:,} VND\n"
                f"🧾 **Mã đơn:** {self.code}\n\n"
                f"📥 **Nội dung CK:** `{self.code}`\n"
                f"#lưu ý: nội dung chuyển khoản không được chỉnh sửa! | "
                f"Và vui lòng chụp bill thanh toán rõ lên trên này nếu gặp lỗi thì admin sẽ giải quyết sớm!"
            ),
            color=discord.Color.green()
        )
        embed.set_image(url=qr)
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        
        if self.code not in bank_waiting:
            bank_waiting[self.code] = {"channel": interaction.channel.id, "link": self.link, "product": self.product, "price": current_price, "user": interaction.user.id}
            db_save_waiting(self.code, interaction.channel.id, self.product, self.link, current_price, interaction.user.id)
        
        asyncio.create_task(bank_countdown(msg, self.code))

    @discord.ui.button(label="🎫 NHẬP VOUCHER", style=discord.ButtonStyle.primary)
    async def input_voucher(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(VoucherModal(self.bot, self.code))

    @discord.ui.button(label="❌ HỦY ĐƠN", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="⚠ XÁC NHẬN HỦY ĐƠN", description="BẠN CÓ CHẮC HỦY ĐƠN HÀNG CHỨ?", color=discord.Color.orange())
        await interaction.response.send_message(embed=embed, view=CancelConfirm(interaction.user.id))

class BuyView(discord.ui.View):
    def __init__(self, bot, bank_price, product, link):
        super().__init__(timeout=None)
        self.bot, self.bank_price, self.product, self.link = bot, bank_price, product, link

    @discord.ui.button(label="🛒 MUA NGAY", style=discord.ButtonStyle.green)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        if not anti_spam_buy(user_id):
            await interaction.response.send_message("⏳ Bạn đang tạo đơn quá nhanh.", ephemeral=True)
            return
        if user_id in user_orders and user_orders[user_id] >= 3:
            await interaction.response.send_message("🚫 Bạn đã đạt giới hạn 3 đơn hàng đang mở.", ephemeral=True)
            return
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="orders") or await guild.create_category("orders")
        order_code = generate_code()
        channel = await guild.create_text_channel(name=f"{order_code}-{interaction.user.name}", category=category)
        await channel.set_permissions(guild.default_role, view_channel=False)
        await channel.set_permissions(interaction.user, view_channel=True, send_messages=True)
        user_orders[user_id] = user_orders.get(user_id, 0) + 1
        
        # Lưu vào bộ nhớ tạm trước để voucher có thể hoạt động
        bank_waiting[order_code] = {"channel": channel.id, "link": self.link, "product": self.product, "price": self.bank_price, "user": interaction.user.id}
        db_save_waiting(order_code, channel.id, self.product, self.link, self.bank_price, interaction.user.id)

        embed = discord.Embed(
            title="# 💳 XÁC NHẬN THANH TOÁN BẰNG NGÂN HÀNG",
            description=(
                f"📦 **Tên hàng:** {self.product}\n"
                f"💰 **Số tiền:** {self.bank_price:,} VND\n"
                f"🆔 **Mã đơn:** {order_code}\n\n"
                f"👇 Chọn phương thức thanh toán\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💡 *Bạn có voucher giảm giá? Hãy nhấp vào **NHẬP VOUCHER** để áp dụng mã ngay.*"
            ),
            color=discord.Color.blue()
        )
        await channel.send(interaction.user.mention, embed=embed, view=PaymentView(self.bot, self.bank_price, self.product, self.link, order_code))
        order_activity[order_code] = False
        asyncio.create_task(auto_close_channel(channel, order_code, user_id))
        await interaction.response.send_message(f"✅ Đơn hàng đã tạo: {channel.mention}", ephemeral=True)

class SellSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id != BANK_CHANNEL_ID: return
        content = message.content.upper()
        matched_code = None
        for code in list(bank_waiting.keys()):
            if code in content:
                matched_code = code
                break
        if matched_code:
            data = bank_waiting[matched_code]
            guild = message.guild
            user_id = data["user"]
            member = guild.get_member(user_id) if guild else None
            channel = self.bot.get_channel(data["channel"])
            
            embed_tkt = discord.Embed(title="🎉 THANH TOÁN THÀNH CÔNG (TỰ ĐỘNG)", description="Hệ thống đã xác nhận giao dịch qua biến động số dư!", color=discord.Color.green())
            embed_tkt.add_field(name="📦 Tên hàng", value=f"{data['product']}", inline=False)
            embed_tkt.add_field(name="💰 Số tiền", value=f"{data['price']:,} VND", inline=True)
            embed_tkt.add_field(name="🆔 Mã đơn", value=f"{matched_code}", inline=True)
            embed_tkt.add_field(name="📥 Link tải", value=f"[Nhấp vào đây để tải]({data['link']})", inline=False)
            if channel:
                try: await channel.send(content=f"<@{user_id}>", embed=embed_tkt)
                except: pass
            
            log_ch = self.bot.get_channel(PAYMENT_LOG_CHANNEL_ID)
            if log_ch: await log_ch.send(f"<@{user_id}> đã thanh toán đơn hàng **{data['product']}** với số tiền **{data['price']:,} VND**, Bạn đánh giá dịch vụ của chúng tớ tại {FEEDBACK_CHANNEL_MENTION} nhé!")
            
            if member:
                role = guild.get_role(PAID_ROLE_ID)
                if role:
                    try: await member.add_roles(role)
                    except: pass
                expiry = (datetime.now() + timedelta(days=3)).timestamp()
                conn = sqlite3.connect('bank_orders.db')
                conn.execute("INSERT OR REPLACE INTO warranty_users VALUES (?, ?, ?)", (user_id, guild.id, expiry))
                conn.commit()
                conn.close()
                try: await member.send(f"Chúc mừng bạn đã mua thành công đơn hàng **{data['product']}** với số tiền **{data['price']:,} VND**. Bạn có **3 ngày bảo hành** từ ***LoTuss's Schematic Shop***. Link tải: {data['link']}")
                except: pass
                
                invite_cog = self.bot.get_cog("InviteSystem")
                if invite_cog: await invite_cog.give_voucher_logic(member, data['product'], data['price'], guild)
            
            db_delete_waiting(matched_code)
            if matched_code in bank_waiting: del bank_waiting[matched_code]
            if user_id in user_orders: user_orders[user_id] = max(0, user_orders[user_id] - 1)
            try: await message.add_reaction("✅")
            except: pass

    @commands.command(name="sellbank")
    @commands.has_permissions(administrator=True)
    async def sellbank(self, ctx, bank_price: int, link: str):
        product = ctx.channel.name
        embed = discord.Embed(
            title="🛒 THANH TOÁN BẰNG CÁCH CHUYỂN KHOẢN NGÂN HÀNG",
            description=(f"📦 **Tên hàng:** {product}\n\n💳 **Số tiền**: {bank_price:,} VND\n\n"
                         "👇 **Nhấn nút MUA NGAY bên dưới để bắt đầu thanh toán**"),
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed, view=BuyView(self.bot, bank_price, product, link))

    @commands.command(name="dabank")
    @commands.has_permissions(administrator=True)
    async def dabank(self, ctx, order_code: str):
        order_code = order_code.upper()
        if order_code not in bank_waiting:
            await ctx.send("❌ Không tìm thấy mã đơn."); return
        data = bank_waiting[order_code]
        user_id, member = data["user"], ctx.guild.get_member(data["user"])
        channel = self.bot.get_channel(data["channel"])
        embed_tkt = discord.Embed(title="🎉 THANH TOÁN THÀNH CÔNG (ADMIN)", description="Admin đã xác nhận giao dịch!", color=discord.Color.green())
        embed_tkt.add_field(name="📦 Tên hàng", value=data["product"], inline=False)
        embed_tkt.add_field(name="💰 Số tiền", value=f"{data['price']:,} VND")
        embed_tkt.add_field(name="🆔 Mã đơn", value=order_code)
        embed_tkt.add_field(name="📥 Link tải", value=f"[Nhấp vào đây]({data['link']})", inline=False)
        if channel: await channel.send(embed=embed_tkt)
        log_ch = self.bot.get_channel(PAYMENT_LOG_CHANNEL_ID)
        if log_ch: await log_ch.send(f"<@{user_id}> đã thanh toán đơn hàng **{data['product']}** với số tiền **{data['price']:,} VND**, Bạn đánh giá dịch vụ của chúng tớ tại {FEEDBACK_CHANNEL_MENTION} nhé!")
        if member:
            role = ctx.guild.get_role(PAID_ROLE_ID)
            if role:
                try: await member.add_roles(role)
                except: pass
                expiry = (datetime.now() + timedelta(days=3)).timestamp()
                conn = sqlite3.connect('bank_orders.db')
                conn.execute("INSERT OR REPLACE INTO warranty_users VALUES (?, ?, ?)", (user_id, ctx.guild.id, expiry))
                conn.commit(); conn.close()
            try: await member.send(f"Chúc mừng bạn đã mua thành công đơn hàng **{data['product']}** với số tiền **{data['price']:,} VND**. Bạn có **3 ngày bảo hành** từ ***LoTuss's Schematic Shop***!")
            except: pass
            invite_cog = self.bot.get_cog("InviteSystem")
            if invite_cog: await invite_cog.give_voucher_logic(member, data['product'], data['price'], ctx.guild)
        db_delete_waiting(order_code)
        del bank_waiting[order_code]
        if user_id in user_orders: user_orders[user_id] = max(0, user_orders[user_id] - 1)
        await ctx.send("✅ Giao dịch thành công.")

async def setup(bot):
    await bot.add_cog(SellSystem(bot))
    if not check_warranty_task.is_running(): check_warranty_task.start(bot)
