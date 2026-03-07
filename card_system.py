import discord
from discord.ext import commands
import random
import string
import asyncio
import aiohttp
import hashlib
import sqlite3
import time

# ==============================
# API CONFIG
# ==============================

PARTNER_ID = "45016810383"
PARTNER_KEY = "0c8672410bf6ba8caeb009508b026ed9"
API_URL = "https://doithes1.vn/chargingws/v2"

WEBHOOK_URL = "https://discord.com/api/webhooks/1479880863243047202/uShjrO4fWTWzCpz2X30-oivNP6XqD224HhpqjBB6oiqUEcE6icMcHR8k728R-1Pv5mlg"

# ==============================
# DATABASE
# ==============================

db = sqlite3.connect("orders.db")
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS orders(
order_code TEXT,
user_id INTEGER,
product TEXT,
price INTEGER,
status TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS revenue(
amount INTEGER
)
""")

db.commit()

# ==============================
# SPAM PROTECTION
# ==============================

cooldown = {}
COOLDOWN_TIME = 10

# ==============================
# UTILS
# ==============================

def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def create_sign(code, serial):
    raw = f"{PARTNER_KEY}{code}{serial}"
    return hashlib.md5(raw.encode()).hexdigest()

async def send_webhook(msg):
    async with aiohttp.ClientSession() as session:
        await session.post(WEBHOOK_URL, json={"content": msg})

# ==============================
# AUTO CHECK CARD
# ==============================

async def auto_check(interaction, params, product, price, order_code, link):

    await asyncio.sleep(10)

    async with aiohttp.ClientSession() as session:
        async with session.get(API_URL, params=params) as resp:
            data = await resp.json()

    status = int(data.get("status", 0))
    real_amount = int(data.get("value", 0))

    if status == 1 and real_amount == price:

        embed = discord.Embed(
            title="✅ Thanh toán thành công",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )

        embed.add_field(name="📦 Sản phẩm", value=product, inline=False)
        embed.add_field(name="💰 Giá", value=f"{price:,} VND")
        embed.add_field(name="🆔 Mã đơn", value=order_code)
        embed.add_field(name="📥 Link nhận", value=link)

        embed.set_footer(text="Card Payment System")

        await interaction.channel.send(embed=embed)

        cursor.execute(
            "UPDATE orders SET status='success' WHERE order_code=?",
            (order_code,)
        )

        cursor.execute("INSERT INTO revenue VALUES(?)", (price,))
        db.commit()

# ==============================
# CANCEL VIEW
# ==============================

class CancelConfirm(discord.ui.View):

    @discord.ui.button(label="Huỷ đơn", style=discord.ButtonStyle.red)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.send_message("Đang huỷ đơn...")

        await asyncio.sleep(3)
        await interaction.channel.delete()

    @discord.ui.button(label="Giữ đơn", style=discord.ButtonStyle.green)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.send_message(
            "Đơn vẫn được giữ",
            ephemeral=True
        )

# ==============================
# CARD MODAL
# ==============================

class CardModal(discord.ui.Modal, title="💳 Thanh toán thẻ cào"):

    telco = discord.ui.TextInput(label="Nhà mạng (VIETTEL/MOBI/VINA)")
    serial = discord.ui.TextInput(label="Serial")
    code = discord.ui.TextInput(label="Mã thẻ")

    def __init__(self, order_code, product, price, link):

        super().__init__()

        self.order_code = order_code
        self.product = product
        self.price = price
        self.link = link

        self.serial.placeholder = f"Nạp đúng mệnh giá: {price:,} VND"

    async def on_submit(self, interaction: discord.Interaction):

        user = interaction.user.id

        if user in cooldown:
            if time.time() - cooldown[user] < COOLDOWN_TIME:

                await interaction.response.send_message(
                    "Bạn đang nạp quá nhanh",
                    ephemeral=True
                )
                return

        cooldown[user] = time.time()

        await interaction.response.defer(ephemeral=True)

        sign = create_sign(self.code.value, self.serial.value)

        params = {

            "telco": self.telco.value.upper(),
            "code": self.code.value,
            "serial": self.serial.value,
            "amount": self.price,
            "request_id": self.order_code,
            "partner_id": PARTNER_ID,
            "sign": sign
        }

        try:

            async with aiohttp.ClientSession() as session:

                async with session.get(API_URL, params=params) as resp:
                    data = await resp.json()

            status = int(data.get("status", 0))
            real_amount = int(data.get("value", 0))

            if status == 1:

                if real_amount != self.price:

                    await interaction.followup.send(
                        f"❌ Thẻ {real_amount:,} không khớp đơn {self.price:,}"
                    )
                    return

                embed = discord.Embed(
                    title="🎉 Thanh toán thành công",
                    color=discord.Color.green()
                )

                embed.add_field(name="📦 Sản phẩm", value=self.product)
                embed.add_field(name="💰 Giá", value=f"{self.price:,} VND")
                embed.add_field(name="📥 Link nhận", value=self.link)

                await interaction.channel.send(embed=embed)

                cursor.execute(
                    "UPDATE orders SET status='success' WHERE order_code=?",
                    (self.order_code,)
                )

                cursor.execute(
                    "INSERT INTO revenue VALUES(?)",
                    (self.price,)
                )

                db.commit()

                await interaction.followup.send("Thẻ hợp lệ")

            elif status == 99:

                await interaction.followup.send(
                    "Thẻ đang xử lý, hệ thống sẽ kiểm tra lại..."
                )

                asyncio.create_task(
                    auto_check(
                        interaction,
                        params,
                        self.product,
                        self.price,
                        self.order_code,
                        self.link
                    )
                )

            else:

                await interaction.followup.send(
                    "❌ Thẻ sai hoặc đã sử dụng"
                )

        except Exception as e:

            await interaction.followup.send(f"Lỗi: {e}")

# ==============================
# PAYMENT VIEW
# ==============================

class CardPaymentView(discord.ui.View):

    def __init__(self, order_code, product, price, link):

        super().__init__(timeout=None)

        self.order_code = order_code
        self.product = product
        self.price = price
        self.link = link

    @discord.ui.button(label="Thanh toán card", style=discord.ButtonStyle.green)
    async def card(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.send_modal(
            CardModal(
                self.order_code,
                self.product,
                self.price,
                self.link
            )
        )

    @discord.ui.button(label="Huỷ đơn", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.send_message(
            "Bạn có chắc muốn huỷ đơn?",
            view=CancelConfirm()
        )

# ==============================
# BUY VIEW
# ==============================

class BuyView(discord.ui.View):

    def __init__(self, price, product, link):

        super().__init__(timeout=None)

        self.price = price
        self.product = product
        self.link = link

    @discord.ui.button(label="🛒 Mua ngay", style=discord.ButtonStyle.green)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):

        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="orders")

        if category is None:
            category = await guild.create_category("orders")

        order_code = generate_code()

        channel = await guild.create_text_channel(
            name=f"{order_code}-{interaction.user.name}",
            category=category
        )

        await channel.set_permissions(guild.default_role, view_channel=False)

        await channel.set_permissions(
            interaction.user,
            view_channel=True,
            send_messages=True
        )

        cursor.execute(
            "INSERT INTO orders VALUES(?,?,?,?,?)",
            (order_code, interaction.user.id, self.product, self.price, "pending")
        )

        db.commit()

        embed = discord.Embed(
            title="🧾 Đơn hàng mới",
            color=discord.Color.blue()
        )

        embed.add_field(name="📦 Sản phẩm", value=self.product, inline=False)
        embed.add_field(name="💰 Giá", value=f"{self.price:,} VND")
        embed.add_field(name="🆔 Mã đơn", value=order_code)

        await channel.send(
            interaction.user.mention,
            embed=embed,
            view=CardPaymentView(
                order_code,
                self.product,
                self.price,
                self.link
            )
        )

        await interaction.response.send_message(
            f"Đơn hàng của bạn: {channel.mention}",
            ephemeral=True
        )

# ==============================
# COMMAND
# ==============================

class CardSystem(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="sellcard")
    async def sellcard(self, ctx, price: int, link: str):

        product = ctx.channel.name

        embed = discord.Embed(
            title="💳 Thanh toán thẻ cào",
            color=discord.Color.blue()
        )

        embed.add_field(name="📦 Sản phẩm", value=product, inline=False)
        embed.add_field(name="💰 Giá", value=f"{price:,} VND")

        embed.set_footer(text="Shop Payment System")

        await ctx.send(
            embed=embed,
            view=BuyView(price, product, link)
        )

async def setup(bot):
    await bot.add_cog(CardSystem(bot))
