import discord
from discord.ext import commands
import random
import string
import asyncio
import requests

BANK = "MB"
ACCOUNT = "0764495919"
ACCOUNT_NAME = "NGUYENTHANHDAT"

# API NAPTHE
API_KEY = "0c8672410bf6ba8caeb009508b026ed9"

ORDERS_CATEGORY_NAME = "orders"

orders = {}

def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


# ==============================
# VIEW MUA SẢN PHẨM
# ==============================

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


# ==============================
# VIEW CHỌN THANH TOÁN
# ==============================

class PaymentView(discord.ui.View):

    def __init__(self, price, product_name, code):
        super().__init__(timeout=None)
        self.price = price
        self.product_name = product_name
        self.code = code


# ==============================
# CHUYỂN KHOẢN
# ==============================

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


# ==============================
# NẠP CARD
# ==============================

    @discord.ui.button(label="🎴 NẠP CARD", style=discord.ButtonStyle.secondary)
    async def card(self, interaction: discord.Interaction, button: discord.ui.Button):

        embed = discord.Embed(
            title="🎴 NẠP THẺ",
            description=(
                "Gửi thẻ theo mẫu:\n\n"
                "```\n"
                "Loaithe Menhgia Seri Mathe\n"
                "```\n"
                "Ví dụ:\n"
                "```\n"
                "VIETTEL 100000 123456789 987654321\n"
                "```"
            ),
            color=discord.Color.orange()
        )

        await interaction.response.send_message(embed=embed)


# ==============================
# GỬI CARD LÊN API
# ==============================

async def send_card_api(network, value, seri, code):

    url = "https://napthe.vn/api/card"

    data = {
        "APIKey": API_KEY,
        "Network": network,
        "CardValue": value,
        "CardSeri": seri,
        "CardCode": code,
        "RequestId": generate_code()
    }

    try:

        res = requests.post(url, json=data).json()

        return res

    except:
        return None


# ==============================
# CHECK MESSAGE CARD
# ==============================

def setup_sell(bot):

    @bot.event
    async def on_message(message):

        if message.author.bot:
            return

        if message.channel.id in orders:

            args = message.content.split()

            if len(args) == 4:

                network = args[0]
                value = args[1]
                seri = args[2]
                code = args[3]

                embed = discord.Embed(
                    title="⏳ ĐANG XỬ LÝ THẺ...",
                    color=discord.Color.yellow()
                )

                msg = await message.channel.send(embed=embed)

                result = await send_card_api(network, value, seri, code)

                if result == None:

                    embed = discord.Embed(
                        title="❌ LỖI API",
                        color=discord.Color.red()
                    )

                    await msg.edit(embed=embed)

                else:

                    if result["status"] == 1:

                        order = orders[message.channel.id]

                        embed = discord.Embed(
                            title="✅ NẠP THẺ THÀNH CÔNG",
                            description=f"📥 Link:\n{order['link']}",
                            color=discord.Color.green()
                        )

                        await msg.edit(embed=embed)

                    else:

                        embed = discord.Embed(
                            title="❌ THẺ KHÔNG HỢP LỆ",
                            color=discord.Color.red()
                        )

                        await msg.edit(embed=embed)

        await bot.process_commands(message)


# ==============================
# LỆNH BÁN
# ==============================

    @bot.command()
    async def sell(ctx, price: int, link: str):

        product_name = ctx.channel.name

        embed = discord.Embed(
            title="🛍️ MUA SẢN PHẨM",
            description=(
                "Nhấn nút bên dưới để mua.\n\n"
                "💳 Chuyển khoản\n"
                "🎴 Nạp card"
            ),
            color=discord.Color.green()
        )

        await ctx.send(
            embed=embed,
            view=BuyView(price, product_name, link)
        )


# ==============================
# ADMIN XÁC NHẬN BANK
# ==============================

    @bot.command()
    @commands.has_permissions(administrator=True)
    async def dabank(ctx):

        if ctx.channel.id not in orders:
            return

        order = orders[ctx.channel.id]

        embed = discord.Embed(
            title="✅ THANH TOÁN THÀNH CÔNG",
            description=f"📥 Link:\n{order['link']}",
            color=discord.Color.green()
        )

        await ctx.send(embed=embed)
