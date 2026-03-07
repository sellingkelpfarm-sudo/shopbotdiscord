import discord
from discord.ext import commands
import random
import string
import asyncio
import aiohttp

API_KEY = "API_KEY_DOITHES1"
PARTNER_ID = "0c8672410bf6ba8caeb009508b026ed9"


def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


# ========================
# CANCEL CONFIRM
# ========================

class CancelConfirm(discord.ui.View):

    @discord.ui.button(label="✅ CÓ", style=discord.ButtonStyle.red)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.send_message("⏳ Kênh sẽ bị xoá sau 5 giây")

        await asyncio.sleep(5)

        await interaction.channel.delete()

    @discord.ui.button(label="❌ KHÔNG", style=discord.ButtonStyle.green)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.send_message(
            "👍 Đơn hàng vẫn được giữ",
            ephemeral=True
        )


# ========================
# CARD MODAL
# ========================

class CardModal(discord.ui.Modal, title="THANH TOÁN CARD"):

    telco = discord.ui.TextInput(label="Nhà mạng (VIETTEL / MOBI / VINA)")
    amount = discord.ui.TextInput(label="Mệnh giá")
    serial = discord.ui.TextInput(label="Serial")
    code = discord.ui.TextInput(label="Mã thẻ")

    def __init__(self, order_code, product, price, link):
        super().__init__()

        self.order_code = order_code
        self.product = product
        self.price = price
        self.link = link

    async def on_submit(self, interaction: discord.Interaction):

        async with aiohttp.ClientSession() as session:

            payload = {
                "partner_id": PARTNER_ID,
                "partner_key": API_KEY,
                "telco": self.telco.value,
                "amount": self.amount.value,
                "serial": self.serial.value,
                "code": self.code.value,
                "command": self.order_code
            }

            async with session.post(
                "https://doithes1.vn/api/card",
                json=payload
            ) as resp:

                data = await resp.json()

        if data.get("status") == "success":

            embed = discord.Embed(
                title="🎉 THANH TOÁN THÀNH CÔNG",
                description="Đã xác nhận giao dịch!",
                color=discord.Color.green()
            )

            embed.add_field(name="📦 Sản phẩm", value=self.product, inline=False)
            embed.add_field(name="💰 Số tiền", value=f"{self.price:,} VND")
            embed.add_field(name="🆔 Mã đơn", value=self.order_code)
            embed.add_field(name="📥 Link tải", value=self.link, inline=False)

            await interaction.channel.send(embed=embed)

            await interaction.response.send_message(
                "✅ Nạp thẻ thành công",
                ephemeral=True
            )

        else:

            await interaction.response.send_message(
                "❌ Thẻ lỗi hoặc đang chờ duyệt",
                ephemeral=True
            )


# ========================
# PAYMENT VIEW
# ========================

class CardPaymentView(discord.ui.View):

    def __init__(self, order_code, product, price, link):
        super().__init__(timeout=None)

        self.order_code = order_code
        self.product = product
        self.price = price
        self.link = link

    @discord.ui.button(label="💳 THANH TOÁN BẰNG CARD", style=discord.ButtonStyle.green)
    async def card(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.send_modal(
            CardModal(
                self.order_code,
                self.product,
                self.price,
                self.link
            )
        )

    @discord.ui.button(label="❌ HỦY ĐƠN HÀNG", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):

        embed = discord.Embed(
            title="⚠ XÁC NHẬN HỦY ĐƠN",
            description="Bạn có chắc muốn hủy đơn?",
            color=discord.Color.orange()
        )

        await interaction.response.send_message(
            embed=embed,
            view=CancelConfirm()
        )


# ========================
# BUY VIEW
# ========================

class BuyView(discord.ui.View):

    def __init__(self, price, product, link):
        super().__init__(timeout=None)

        self.price = price
        self.product = product
        self.link = link

    @discord.ui.button(label="🛒 MUA NGAY", style=discord.ButtonStyle.green)
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

        embed = discord.Embed(
            title="🧾 TẠO ĐƠN HÀNG",
            description=(
                f"📦 **Sản phẩm:** {self.product}\n"
                f"💰 **Giá:** {self.price:,} VND\n"
                f"🆔 **Mã đơn:** {order_code}\n\n"
                "👇 Chọn phương thức thanh toán"
            ),
            color=discord.Color.blue()
        )

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
            f"✅ Đơn hàng: {channel.mention}",
            ephemeral=True
        )


# ========================
# COG
# ========================

class CardSystem(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="sellcard")
    async def sellcard(self, ctx, price: int, link: str):

        product = ctx.channel.name

        embed = discord.Embed(
            title="💳 THANH TOÁN BẰNG CARD",
            description=(
                f"📦 **Sản phẩm:** {product}\n"
                f"💰 **Giá:** {price:,} VND\n\n"
                "👇 Nhấn **MUA NGAY** để tạo đơn"
            ),
            color=discord.Color.blue()
        )

        await ctx.send(
            embed=embed,
            view=BuyView(price, product, link)
        )


async def setup(bot):
    await bot.add_cog(CardSystem(bot))
