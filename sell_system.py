import discord
from discord.ext import commands
import random
import string

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

    @discord.ui.button(label="MUA", style=discord.ButtonStyle.success)
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

        price_text = f"{self.price:,}".replace(",", ".") + "VND"

        embed = discord.Embed(
            title=f"XÁC NHẬN THANH TOÁN ĐƠN HÀNG {self.product_name}",
            description=(
                f"Tên đơn hàng: {self.product_name}\n"
                f"Số Tiền: {price_text}\n"
                f"Mã Giao Dịch: {code}"
            ),
            color=discord.Color.orange()
        )

        await channel.send(
            content=user.mention,
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

    @discord.ui.button(label="XÁC NHẬN GIAO DỊCH", style=discord.ButtonStyle.primary)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):

        vietqr = f"https://img.vietqr.io/image/{BANK}-{ACCOUNT}-compact2.png?amount={self.price}&addInfo=MaDonHang_{self.code}&accountName={ACCOUNT_NAME}"

        price_text = f"{self.price:,}".replace(",", ".") + "VND"

        embed = discord.Embed(
            title="VUI LÒNG QUÉT MÃ QR Ở DƯỚI ĐÂY ĐỂ THANH TOÁN",
            description=(
                f"Tên đơn hàng: {self.product_name}\n"
                f"Số Tiền: {price_text}\n"
                f"Mã Giao Dịch: {self.code}\n\n"
                f"#Lưu ý: Không chỉnh sửa nội dung chuyển khoản!!!\n\n"
                f"#*sau khi thực hiện quét mã thành công thì admin sẽ check và xác nhận giao dịch thủ công bạn nhé! ^w^*\n\n"
                f"⏳ Thời gian thanh toán: **5 phút**"
            ),
            color=discord.Color.green()
        )

        embed.set_image(url=vietqr)

        qr_message = await interaction.response.send_message(embed=embed)

        # Lấy message vừa gửi
        qr_message = await interaction.original_response()

        # Đợi 5 phút
        await asyncio.sleep(300)

        try:
            await qr_message.delete()
            await interaction.channel.send(
                "⚠ **ĐÃ QUÁ GIỜ THỰC HIỆN GIAO DỊCH. VUI LÒNG THỬ LẠI.**"
            )
        except:
            pass

def setup_sell(bot):

    @bot.command()
    async def sell(ctx, price: int, link: str):

        product_name = ctx.channel.name

        embed = discord.Embed(
            description='Vui lòng chọn nút **"MUA"** ở dưới đây để bắt đầu mua.',
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

        price_text = f"{order['price']:,}".replace(",", ".") + "VND"

        embed = discord.Embed(
            title="XÁC NHẬN THANH TOÁN THÀNH CÔNG",
            description=(
                f"Tên đơn hàng: {order['product']}\n"
                f"Số Tiền: {price_text}\n"
                f"Mã Giao Dịch: {order['code']}\n\n"

                f"Link tải: {order['link']}\n"

                "_+_+_+_+_+_+_+_+_+_+_+_+_+_+_+_+_+_+_+_+_+_+_\n"
                "CẢM ƠN BẠN ĐÃ TIN TƯỞNG LỰA CHỌN SHOP SCHEMATICS CỦA CHÚNG TÔI!"
            ),
            color=discord.Color.green()
        )

        await ctx.send(embed=embed)
