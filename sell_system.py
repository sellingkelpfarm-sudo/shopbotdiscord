import discord
from discord.ext import commands
import random
import string
import asyncio

BANK = "MB"
ACCOUNT = "0764495919"
ACCOUNT_NAME = "NGUYENTHANHDAT"

ORDERS_CATEGORY_NAME = "orders"

orders = {}

def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


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
            name=code,
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
            title="🧾 TẠO ĐƠN HÀNG THÀNH CÔNG",
            description=(
                f"📦 **Sản phẩm:** `{self.product_name}`\n"
                f"💰 **Giá:** `{price_text}`\n"
                f"🆔 **Mã giao dịch:** `{code}`\n\n"
                "👉 Nhấn **XÁC NHẬN GIAO DỊCH** để lấy mã QR thanh toán."
            ),
            color=discord.Color.orange()
        )

        await channel.send(
            content=f"👤 {user.mention}",
            embed=embed,
            view=ConfirmView(self.price, self.product_name, code)
        )

        await interaction.response.send_message(
            f"✅ Đã tạo kênh thanh toán: {channel.mention}",
            ephemeral=True
        )


class ConfirmView(discord.ui.View):
    def __init__(self, price, product_name, code):
        super().__init__(timeout=None)
        self.price = price
        self.product_name = product_name
        self.code = code

    @discord.ui.button(label="💳 XÁC NHẬN GIAO DỊCH", style=discord.ButtonStyle.primary)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):

        vietqr = f"https://img.vietqr.io/image/{BANK}-{ACCOUNT}-compact2.png?amount={self.price}&addInfo=MaDonHang_{self.code}&accountName={ACCOUNT_NAME}"

        price_text = f"{self.price:,}".replace(",", ".") + "VND"

        embed = discord.Embed(
            title="💳 THANH TOÁN ĐƠN HÀNG",
            color=discord.Color.green()
        )

        embed.set_image(url=vietqr)

        await interaction.response.send_message(embed=embed)

        qr_message = await interaction.original_response()

        time_left = 300

        while time_left > 0:

            minutes = time_left // 60
            seconds = time_left % 60

            embed.description = (
                f"📦 **Tên đơn hàng:** {self.product_name}\n"
                f"💰 **Số tiền:** {price_text}\n"
                f"🆔 **Mã giao dịch:** {self.code}\n\n"

                "⚠ **Lưu ý:**\n"
                "• Không chỉnh sửa nội dung chuyển khoản\n"
                "• Thanh toán đúng số tiền\n\n"

                f"⏳ **Thời gian còn lại:** `{minutes:02}:{seconds:02}`"
            )

            await qr_message.edit(embed=embed)

            await asyncio.sleep(1)

            time_left -= 1

        try:
            await qr_message.delete()

            timeout_embed = discord.Embed(
                title="⏰ ĐƠN HÀNG HẾT HẠN",
                description="⚠ **ĐÃ QUÁ GIỜ THỰC HIỆN GIAO DỊCH. VUI LÒNG THỬ LẠI.**",
                color=discord.Color.red()
            )

            await interaction.channel.send(embed=timeout_embed)

        except:
            pass


def setup_sell(bot):

    @bot.command()
    async def sell(ctx, price: int, link: str):

        product_name = ctx.channel.name

        embed = discord.Embed(
            title="🛍️ MUA SẢN PHẨM",
            description=(
                "Nhấn nút **🛒 MUA NGAY** bên dưới để tạo đơn hàng.\n\n"
                "📌 Sau khi tạo đơn bạn sẽ nhận được **QR thanh toán**."
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
            await ctx.send("❌ Không tìm thấy dữ liệu đơn hàng.")
            return

        order = orders[ctx.channel.id]

        price_text = f"{order['price']:,}".replace(",", ".") + " VND"

        embed = discord.Embed(
            title="✅ THANH TOÁN THÀNH CÔNG",
            description=(
                f"📦 **Sản phẩm:** `{order['product']}`\n"
                f"💰 **Số tiền:** `{price_text}`\n"
                f"🆔 **Mã giao dịch:** `{order['code']}`\n\n"

                f"📥 **Link tải:**\n{order['link']}\n\n"

                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "💚 **CẢM ƠN BẠN ĐÃ ỦNG HỘ SHOP!**"
            ),
            color=discord.Color.green()
        )

        await ctx.send(embed=embed)
