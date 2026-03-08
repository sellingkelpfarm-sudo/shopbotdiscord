import discord
from discord.ext import commands
import random
import string
import asyncio
import aiohttp
import hashlib
import sqlite3
import time

PARTNER_ID = "45016810383"
PARTNER_KEY = "0c8672410bf6ba8caeb009508b026ed9"

API_URL = "https://doithe1s.vn/chargingws/v2"

CALLBACK_URL = "https://shopbotdiscord.railway.app/charge/callback"

WEBHOOK_URL = "https://discord.com/api/webhooks/1479880863243047202/uShjrO4fWTWzCpz2X30-oivNP6XqD224HhpqjBB6oiqUEcE6icMcHR8k728R-1Pv5mlg"

db = sqlite3.connect("orders.db", check_same_thread=False)
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS orders(
order_code TEXT,
user_id INTEGER,
product TEXT,
price INTEGER,
status TEXT,
telco TEXT,
serial TEXT,
code TEXT,
link TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS revenue(
amount INTEGER
)
""")

db.commit()

cooldown = {}
buy_cooldown = {}
COOLDOWN_TIME = 10

order_activity = {}
ORDER_TIMEOUT = 900


def generate_code():
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        cursor.execute("SELECT order_code FROM orders WHERE order_code=?", (code,))
        if cursor.fetchone() is None:
            return code


# FIX SIGN API
def create_sign(telco, code, serial):
    raw = f"{telco}{code}{serial}{PARTNER_KEY}"
    return hashlib.md5(raw.encode()).hexdigest()


async def send_webhook(msg):
    async with aiohttp.ClientSession() as session:
        await session.post(WEBHOOK_URL, json={"content": msg})


async def auto_close_channel(channel, order_code):

    await asyncio.sleep(ORDER_TIMEOUT)

    if order_code in order_activity and not order_activity[order_code]:

        try:
            await channel.send("⌛ Đơn hàng đã bị đóng do không thanh toán trong 15 phút.")
            await asyncio.sleep(5)
            await channel.delete()
        except:
            pass


class CancelConfirmView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=30)

    @discord.ui.button(label="CÓ", style=discord.ButtonStyle.red)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.send_message("🗑 Kênh sẽ bị xóa sau 5 giây...")

        await asyncio.sleep(5)

        await interaction.channel.delete()

    @discord.ui.button(label="KHÔNG", style=discord.ButtonStyle.gray)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.send_message(
            "✅ Đã giữ lại đơn hàng.",
            ephemeral=True
        )


class CardModal(discord.ui.Modal, title="💳 NẠP THẺ CÀO"):

    serial = discord.ui.TextInput(
        label="Serial",
        placeholder="Nhập serial thẻ",
        required=True
    )

    code = discord.ui.TextInput(
        label="Mã thẻ",
        placeholder="Nhập mã thẻ",
        required=True
    )

    def __init__(self, telco, order_code, product, price, link):

        super().__init__()

        self.telco = telco
        self.order_code = order_code
        self.product = product
        self.price = price
        self.link = link

    async def on_submit(self, interaction: discord.Interaction):

        order_activity[self.order_code] = True

        user = interaction.user.id

        if user in cooldown:
            if time.time() - cooldown[user] < COOLDOWN_TIME:

                await interaction.response.send_message(
                    "⏱ Bạn đang nạp quá nhanh",
                    ephemeral=True
                )
                return

        cooldown[user] = time.time()

        await interaction.response.defer(ephemeral=True)

        sign = create_sign(self.telco, self.code.value, self.serial.value)

        params = {
            "command": "charging",
            "partner_id": PARTNER_ID,
            "telco": self.telco,
            "code": self.code.value,
            "serial": self.serial.value,
            "amount": self.price,
            "request_id": self.order_code,
            "callback_url": CALLBACK_URL,
            "sign": sign
        }

        cursor.execute("""
UPDATE orders 
SET telco=?,serial=?,code=?,link=? 
WHERE order_code=?
""", (self.telco, self.serial.value, self.code.value, self.link, self.order_code))

        db.commit()

        try:

            async with aiohttp.ClientSession() as session:

                async with session.get(API_URL, params=params) as resp:

                    if resp.content_type != "application/json":

                        await interaction.followup.send(
                            "❌ API thẻ đang lỗi hoặc bảo trì."
                        )
                        return

                    data = await resp.json()

        except:

            await interaction.followup.send(
                "❌ Không thể kết nối API nạp thẻ."
            )
            return

        status = int(data.get("status", 0))

        if status == 99:

            await interaction.followup.send(
                "✅ Đã gửi thẻ thành công\n⏳ Đang chờ hệ thống xác nhận"
            )

        elif status == 1:

            await interaction.followup.send("✅ Thẻ hợp lệ")

            cursor.execute(
                "INSERT INTO revenue VALUES(?)",
                (self.price,)
            )

            db.commit()

        else:

            await interaction.followup.send(
                "❌ Thẻ sai hoặc đã sử dụng"
            )


class TelcoSelect(discord.ui.Select):

    def __init__(self, order_code, product, price, link):

        options = [

            discord.SelectOption(label="Garena", value="GARENA"),
            discord.SelectOption(label="Viettel", value="VIETTEL"),
            discord.SelectOption(label="Vinaphone", value="VINA"),
            discord.SelectOption(label="Mobifone", value="MOBI"),
            discord.SelectOption(label="Vcoin", value="VCOIN"),
            discord.SelectOption(label="Scoin", value="SCOIN"),
            discord.SelectOption(label="Zing", value="ZING"),
        ]

        super().__init__(placeholder="📡 Chọn loại thẻ", options=options)

        self.order_code = order_code
        self.product = product
        self.price = price
        self.link = link

    async def callback(self, interaction: discord.Interaction):

        await interaction.response.send_modal(
            CardModal(
                self.values[0],
                self.order_code,
                self.product,
                self.price,
                self.link
            )
        )


class TelcoView(discord.ui.View):

    def __init__(self, order_code, product, price, link):

        super().__init__(timeout=None)

        self.add_item(
            TelcoSelect(order_code, product, price, link)
        )


class CardPaymentView(discord.ui.View):

    def __init__(self, order_code, product, price, link):

        super().__init__(timeout=None)

        self.order_code = order_code
        self.product = product
        self.price = price
        self.link = link

    @discord.ui.button(label="💳 THANH TOÁN CARD", style=discord.ButtonStyle.green)
    async def card(self, interaction: discord.Interaction, button: discord.ui.Button):

        order_activity[self.order_code] = True

        await interaction.response.send_message(
            "📡 Chọn loại thẻ:",
            view=TelcoView(
                self.order_code,
                self.product,
                self.price,
                self.link
            ),
            ephemeral=True
        )

    @discord.ui.button(label="❌ HỦY ĐƠN", style=discord.ButtonStyle.red)
    async def cancel_order(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.send_message(
            "⚠️ BẠN CÓ CHẮC HỦY ĐƠN HÀNG CHỨ?",
            view=CancelConfirmView(),
            ephemeral=True
        )


class BuyView(discord.ui.View):

    def __init__(self, price, product, link):

        super().__init__(timeout=None)

        self.price = price
        self.product = product
        self.link = link

    @discord.ui.button(label="🛒 MUA NGAY", style=discord.ButtonStyle.green)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.defer(ephemeral=True)

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
            "INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?)",
            (order_code, interaction.user.id, self.product, self.price, "pending", "", "", "", self.link)
        )

        db.commit()

        embed = discord.Embed(
            title="🧾 TẠO ĐƠN HÀNG",
            color=discord.Color.blurple()
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

        order_activity[order_code] = False

        asyncio.create_task(
            auto_close_channel(channel, order_code)
        )

        await interaction.followup.send(
            f"✅ Đơn của bạn: {channel.mention}",
            ephemeral=True
        )


class CardSystem(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="sellcard")
    async def sellcard(self, ctx, price: int, link: str):

        product = ctx.channel.name

        embed = discord.Embed(
            title="💳 Thanh toán thẻ cào",
            color=discord.Color.blurple()
        )

        embed.add_field(name="📦 Sản phẩm", value=product, inline=False)
        embed.add_field(name="💰 Giá", value=f"{price:,} VND")
        embed.add_field(name="👇", value="Nhấn **MUA NGAY** để tạo đơn", inline=False)

        await ctx.send(
            embed=embed,
            view=BuyView(price, product, link)
        )


async def setup(bot):
    if not bot.get_cog("CardSystem"):
        await bot.add_cog(CardSystem(bot))
