import discord
from discord.ext import commands
import requests
import random
import string
import time
import asyncio

API_KEY = "0c8672410bf6ba8caeb009508b026ed9"

cooldowns = {}
card_queue = asyncio.Queue()

orders = {}  # NEW: lưu đơn hàng bank


def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


def anti_spam(user_id):

    now = time.time()

    if user_id in cooldowns:
        if now - cooldowns[user_id] < 10:
            return False

    cooldowns[user_id] = now
    return True


# ======================
# CANCEL CONFIRM
# ======================

class CancelConfirm(discord.ui.View):

    @discord.ui.button(label="✅ CÓ", style=discord.ButtonStyle.red)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.send_message("⏳ Kênh sẽ bị xoá sau 5 giây.")

        await asyncio.sleep(5)

        await interaction.channel.delete()

    @discord.ui.button(label="❌ KHÔNG", style=discord.ButtonStyle.green)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.send_message(
            "👍 Đơn hàng vẫn được giữ.",
            ephemeral=True
        )


# ======================
# BANK TIMER
# ======================

async def bank_countdown(message):

    seconds = 300

    while seconds > 0:

        m = seconds // 60
        s = seconds % 60

        embed = message.embeds[0]

        embed.set_footer(text=f"⏳ Thời gian còn lại: {m:02}:{s:02}")

        await message.edit(embed=embed)

        await asyncio.sleep(1)

        seconds -= 1

    embed = discord.Embed(
        title="❌ QUÁ THỜI GIAN THỰC HIỆN CHUYỂN KHOẢN",
        description="Vui lòng thử lại!",
        color=discord.Color.red()
    )

    await message.edit(embed=embed, view=None)


# ======================
# CARD MODAL
# ======================

class CardModal(discord.ui.Modal):

    def __init__(self, price, order_id, product, link):
        super().__init__(title="🎴 NẠP THẺ CÀO")

        self.price = price
        self.order_id = order_id
        self.product = product
        self.link = link

        self.telco = discord.ui.TextInput(
            label="Loại thẻ",
            placeholder="VIETTEL / MOBIFONE / VINAPHONE"
        )

        self.serial = discord.ui.TextInput(
            label="Số seri thẻ"
        )

        self.code = discord.ui.TextInput(
            label="Mã thẻ"
        )

        self.add_item(self.telco)
        self.add_item(self.serial)
        self.add_item(self.code)

    async def on_submit(self, interaction: discord.Interaction):

        embed = discord.Embed(
            title="⏳ ĐANG KIỂM TRA THẺ...",
            description=(
                f"📦 Sản phẩm: {self.product}\n"
                f"💰 Mệnh giá: {self.price:,} VND\n"
                f"🧾 Mã đơn: {self.order_id}"
            ),
            color=discord.Color.yellow()
        )

        await interaction.response.send_message(embed=embed)

        await card_queue.put({
            "interaction": interaction,
            "telco": self.telco.value,
            "serial": self.serial.value,
            "code": self.code.value,
            "price": self.price,
            "product": self.product,
            "link": self.link,
            "order": self.order_id
        })


# ======================
# PAYMENT VIEW
# ======================

class PaymentView(discord.ui.View):

    def __init__(self, bank_price, card_price, product, link, order_code):
        super().__init__(timeout=None)

        self.bank_price = bank_price
        self.card_price = card_price
        self.product = product
        self.link = link
        self.code = order_code

    @discord.ui.button(label="💳 CHUYỂN KHOẢN", style=discord.ButtonStyle.green)
    async def bank(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not anti_spam(interaction.user.id):

            await interaction.response.send_message(
                "⏳ Bạn thao tác quá nhanh.",
                ephemeral=True
            )
            return

        qr = f"https://img.vietqr.io/image/MB-0764495919-compact2.png?amount={self.bank_price}&addInfo=DH{self.code}"

        embed = discord.Embed(
            title="💳 THANH TOÁN CHUYỂN KHOẢN",
            description=(
                f"📦 **Sản phẩm:** {self.product}\n"
                f"💰 **Số tiền:** {self.bank_price:,} VND\n"
                f"🧾 **Mã đơn:** {self.code}\n\n"
                f"📥 Nội dung CK: **DH{self.code}**"
            ),
            color=discord.Color.green()
        )

        embed.set_image(url=qr)

        await interaction.response.send_message(embed=embed)

        msg = await interaction.original_response()

        asyncio.create_task(bank_countdown(msg))

    @discord.ui.button(label="🎴 NẠP CARD", style=discord.ButtonStyle.blurple)
    async def card(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not anti_spam(interaction.user.id):

            await interaction.response.send_message(
                "⏳ Bạn thao tác quá nhanh.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            CardModal(
                self.card_price,
                self.code,
                self.product,
                self.link
            )
        )

    @discord.ui.button(label="❌ HỦY ĐƠN", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):

        embed = discord.Embed(
            title="⚠ XÁC NHẬN HỦY ĐƠN",
            description="Bạn có chắc muốn hủy đơn hàng?",
            color=discord.Color.orange()
        )

        await interaction.response.send_message(
            embed=embed,
            view=CancelConfirm()
        )


# ======================
# BUY VIEW
# ======================

class BuyView(discord.ui.View):

    def __init__(self, bank_price, card_price, product, link):

        super().__init__(timeout=None)

        self.bank_price = bank_price
        self.card_price = card_price
        self.product = product
        self.link = link

    @discord.ui.button(label="🛒 MUA NGAY", style=discord.ButtonStyle.green)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):

        guild = interaction.guild

        category = discord.utils.get(guild.categories, name="orders")

        if category is None:
            category = await guild.create_category("orders")

        order_code = generate_code()

        channel = await guild.create_text_channel(  # EDIT
            name=f"{order_code}-{interaction.user.name}".lower(),
            category=category
        )

        await channel.set_permissions(guild.default_role, view_channel=False)

        await channel.set_permissions(
            interaction.user,
            view_channel=True,
            send_messages=True
        )

        orders[order_code] = {  # NEW
            "channel": channel,
            "link": self.link
        }

        embed = discord.Embed(
            title="🧾 TẠO ĐƠN HÀNG",
            description=(
                f"📦 **Sản phẩm:** {self.product}\n"
                f"💰 **Giá:** {self.bank_price:,} VND\n"
                f"🆔 **Mã đơn:** {order_code}\n\n"
                "👇 Chọn phương thức thanh toán"
            ),
            color=discord.Color.blue()
        )

        await channel.send(
            interaction.user.mention,
            embed=embed,
            view=PaymentView(
                self.bank_price,
                self.card_price,
                self.product,
                self.link,
                order_code
            )
        )

        await interaction.response.send_message(
            f"✅ Đơn hàng đã tạo: {channel.mention}",
            ephemeral=True
        )


# ======================
# CARD WORKER
# ======================

async def card_worker(bot):

    while True:

        data = await card_queue.get()

        url = "https://napthe.vn/api/card"

        payload = {
            "APIKey": API_KEY,
            "Network": data["telco"],
            "CardValue": data["price"],
            "CardSeri": data["serial"],
            "CardCode": data["code"],
            "RequestId": data["order"]
        }

        try:

            res = requests.post(url, json=payload).json()

            if res.get("status") == 1:

                embed = discord.Embed(
                    title="✅ THANH TOÁN THÀNH CÔNG",
                    description=f"📥 Link tải:\n{data['link']}",
                    color=discord.Color.green()
                )

                await data["interaction"].followup.send(embed=embed)

            else:

                embed = discord.Embed(
                    title="❌ THẺ KHÔNG HỢP LỆ",
                    description="Vui lòng kiểm tra lại thẻ.",
                    color=discord.Color.red()
                )

                await data["interaction"].followup.send(embed=embed)

        except:

            embed = discord.Embed(
                title="❌ LỖI API",
                description="Không thể kết nối API.",
                color=discord.Color.red()
            )

            await data["interaction"].followup.send(embed=embed)

        await asyncio.sleep(5)


# ======================
# SELL SYSTEM
# ======================

class SellSystem(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        bot.loop.create_task(card_worker(bot))

    @commands.command()
    async def sell(self, ctx, bank_price: int, card_price: int, *, link: str):  # EDIT (không cần tên sản phẩm)

        product = ctx.channel.name  # NEW: lấy tên bài viết forum

        embed = discord.Embed(
            title="🛒 SẢN PHẨM",
            description=(
                f"📦 **Sản phẩm:** {product}\n\n"
                f"💳 Chuyển khoản: {bank_price:,} VND\n"
                f"🎴 Nạp card: {card_price:,} VND\n\n"
                "👇 Nhấn MUA NGAY để tạo đơn"
            ),
            color=discord.Color.blue()
        )

        await ctx.send(
            embed=embed,
            view=BuyView(bank_price, card_price, product, link)
        )

    # NEW: xác nhận bank thủ công
    @commands.command()
    async def dabank(self, ctx, order_code: str):

        order_code = order_code.upper()

        if order_code not in orders:
            await ctx.send("❌ Không tìm thấy đơn.")
            return

        data = orders[order_code]

        embed = discord.Embed(
            title="✅ THANH TOÁN THÀNH CÔNG",
            description=f"📥 Link tải:\n{data['link']}",
            color=discord.Color.green()
        )

        await data["channel"].send(embed=embed)


async def setup(bot):
    await bot.add_cog(SellSystem(bot))
