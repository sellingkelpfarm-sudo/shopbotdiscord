import discord
from discord.ext import commands
import random
import string
import requests

BANK = "MB"
ACCOUNT = "0764495919"
ACCOUNT_NAME = "NGUYENTHANHDAT"

API_KEY = "0c8672410bf6ba8caeb009508b026ed9"

ORDERS_CATEGORY_NAME = "orders"

orders = {}


def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


# ===================================
# MODAL NẠP CARD
# ===================================

class CardModal(discord.ui.Modal, title="🎴 NẠP THẺ CÀO"):

    telco = discord.ui.TextInput(
        label="Loại thẻ",
        placeholder="VIETTEL / MOBIFONE / VINAPHONE"
    )

    amount = discord.ui.TextInput(
        label="Mệnh giá",
        placeholder="100000"
    )

    serial = discord.ui.TextInput(
        label="Số seri"
    )

    code = discord.ui.TextInput(
        label="Mã thẻ"
    )

    async def on_submit(self, interaction: discord.Interaction):

        embed = discord.Embed(
            title="⏳ ĐANG XỬ LÝ THẺ...",
            color=discord.Color.yellow()
        )

        await interaction.response.send_message(embed=embed)

        url = "https://napthe.vn/api/card"

        data = {
            "APIKey": API_KEY,
            "Network": self.telco.value,
            "CardValue": self.amount.value,
            "CardSeri": self.serial.value,
            "CardCode": self.code.value,
            "RequestId": generate_code()
        }

        try:

            res = requests.post(url, json=data).json()

            if res["status"] == 1:

                order = orders.get(interaction.channel.id)

                embed = discord.Embed(
                    title="✅ NẠP THẺ THÀNH CÔNG",
                    description=f"📥 Link tải:\n{order['link']}",
                    color=discord.Color.green()
                )

                await interaction.followup.send(embed=embed)

            else:

                embed = discord.Embed(
                    title="❌ THẺ KHÔNG HỢP LỆ",
                    description="Vui lòng kiểm tra lại thẻ.",
                    color=discord.Color.red()
                )

                await interaction.followup.send(embed=embed)

        except:

            embed = discord.Embed(
                title="❌ LỖI API",
                description="Không thể kết nối máy chủ nạp thẻ.",
                color=discord.Color.red()
            )

            await interaction.followup.send(embed=embed)


# ===================================
# VIEW CHỌN THANH TOÁN
# ===================================

class PaymentView(discord.ui.View):

    def __init__(self, price, product_name, code):
        super().__init__(timeout=None)
        self.price = price
        self.product_name = product_name
        self.code = code

    @discord.ui.button(label="💳 CHUYỂN KHOẢN", style=discord.ButtonStyle.primary)
    async def bank(self, interaction: discord.Interaction, button: discord.ui.Button):

        vietqr = f"https://img.vietqr.io/image/{BANK}-{ACCOUNT}-compact2.png?amount={self.price}&addInfo=DH_{self.code}&accountName={ACCOUNT_NAME}"

        embed = discord.Embed(
            title="💳 THANH TOÁN QR",
            description=(
                f"📦 **Sản phẩm:** {self.product_name}\n"
                f"💰 **Số tiền:** {self.price} VND\n"
                f"🆔 **Nội dung CK:** DH_{self.code}"
            ),
            color=discord.Color.green()
        )

        embed.set_image(url=vietqr)

        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="🎴 NẠP CARD", style=discord.ButtonStyle.secondary)
    async def card(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.send_modal(CardModal())


# ===================================
# VIEW MUA HÀNG
# ===================================

class BuyView(discord.ui.View):

    def __init__(self, price, product_name, download_link):
        super().__init__(timeout=None)
        self.price = price
        self.product_name = product_name
        self.download_link = download_link

    @discord.ui.button(label="🛒 MUA NGAY", style=discord.ButtonStyle.success)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):

        guild = interaction.guild
        user = interaction.user
        code = generate_code()

        category = discord.utils.get(guild.categories, name=ORDERS_CATEGORY_NAME)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True)
        }

        channel = await guild.create_text_channel(
            name=f"order-{code}",
            category=category,
            overwrites=overwrites
        )

        orders[channel.id] = {
            "code": code,
            "price": self.price,
            "product": self.product_name,
            "buyer": user.id,
            "link": self.download_link
        }

        price_text = f"{self.price:,}".replace(",", ".") + " VND"

        embed = discord.Embed(
            title="🧾 TẠO ĐƠN HÀNG",
            description=(
                f"📦 **Sản phẩm:** {self.product_name}\n"
                f"💰 **Giá:** {price_text}\n"
                f"🆔 **Mã đơn:** {code}\n\n"
                "👇 Chọn phương thức thanh toán"
            ),
            color=discord.Color.orange()
        )

        await channel.send(
            content=user.mention,
            embed=embed,
            view=PaymentView(self.price, self.product_name, code)
        )

        await interaction.response.send_message(
            f"✅ Đã tạo đơn: {channel.mention}",
            ephemeral=True
        )


# ===================================
# SETUP SELL
# ===================================

def setup_sell(bot):

    @bot.command()
    async def sell(ctx, price: int, link: str):

        product_name = ctx.channel.name

        embed = discord.Embed(
            title="🛍️ MUA SẢN PHẨM",
            description=(
                "Nhấn nút bên dưới để mua.\n\n"
                "💳 Thanh toán QR\n"
                "🎴 Nạp thẻ cào"
            ),
            color=discord.Color.green()
        )

        await ctx.send(
            embed=embed,
            view=BuyView(price, product_name, link)
        )

    @bot.command()
    @commands.has_permissions(administrator=True)
    async def dabank(ctx):

        if ctx.channel.id not in orders:
            return

        order = orders[ctx.channel.id]

        embed = discord.Embed(
            title="✅ THANH TOÁN THÀNH CÔNG",
            description=f"📥 Link tải:\n{order['link']}",
            color=discord.Color.green()
        )

        await ctx.send(embed=embed)
