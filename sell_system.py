import discord
from discord.ext import commands
import random
import string
import time
import asyncio

cooldowns = {}
bank_waiting = {}

# ID KÊNH WEBHOOK BIẾN ĐỘNG SỐ DƯ
BANK_CHANNEL_ID = 1479440469120389221


# ======================
# GENERATE ORDER CODE (ANTI DUPLICATE)
# ======================

def generate_code():

    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

        if code not in bank_waiting:
            return code


# ======================
# ANTI SPAM
# ======================

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

async def bank_countdown(message, order_code):

    seconds = 300

    while seconds > 0:

        if order_code not in bank_waiting:
            return

        m = seconds // 60
        s = seconds % 60

        embed = message.embeds[0]

        embed.set_footer(text=f"⏳ Thời gian còn lại: {m:02}:{s:02}")

        await message.edit(embed=embed)

        await asyncio.sleep(1)

        seconds -= 1

    if order_code in bank_waiting:
        del bank_waiting[order_code]

    embed = discord.Embed(
        title="❌ QUÁ THỜI GIAN CHUYỂN KHOẢN",
        description="Vui lòng tạo lại đơn!",
        color=discord.Color.red()
    )

    await message.edit(embed=embed, view=None)


# ======================
# PAYMENT VIEW
# ======================

class PaymentView(discord.ui.View):

    def __init__(self, bank_price, product, link, order_code):
        super().__init__(timeout=None)

        self.bank_price = bank_price
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

        qr = f"https://img.vietqr.io/image/MB-0764495919-compact2.png?amount={self.bank_price}&addInfo={self.code}"

        embed = discord.Embed(
            title="💳 THANH TOÁN CHUYỂN KHOẢN",
            description=(
                f"📦 **Sản phẩm:** {self.product}\n"
                f"💰 **Số tiền:** {self.bank_price:,} VND\n"
                f"🧾 **Mã đơn:** {self.code}\n\n"
                f"📥 **Nội dung CK:** `{self.code}`"
                
                f"#lưu ý: nội dung chuyển khoản không được chỉnh sửa!!!"
            ),
            color=discord.Color.green()
        )

        embed.set_image(url=qr)

        await interaction.response.send_message(embed=embed)

        msg = await interaction.original_response()

        bank_waiting[self.code] = {
            "channel": interaction.channel.id,
            "link": self.link,
            "product": self.product,
            "price": self.bank_price
        }

        asyncio.create_task(bank_countdown(msg, self.code))

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

    def __init__(self, bank_price, product, link):

        super().__init__(timeout=None)

        self.bank_price = bank_price
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
# SELL SYSTEM
# ======================

class SellSystem(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="sellbank")
    async def sellbank(self, ctx, bank_price: int, link: str):

        product = ctx.channel.name

        embed = discord.Embed(
            title="🛒 SẢN PHẨM",
            description=(
                f"📦 **Sản phẩm:** {product}\n\n"
                f"💳 Chuyển khoản: {bank_price:,} VND\n\n"
                "👇 Nhấn MUA NGAY để tạo đơn"
            ),
            color=discord.Color.blue()
        )

        await ctx.send(
            embed=embed,
            view=BuyView(bank_price, product, link)
        )

    @commands.command(name="dabank")
    @commands.has_permissions(administrator=True)
    async def dabank(self, ctx, order_code: str):

        order_code = order_code.upper()

        if order_code not in bank_waiting:
            await ctx.send("❌ Không tìm thấy mã đơn này.")
            return

        data = bank_waiting[order_code]

        channel = self.bot.get_channel(data["channel"])

        embed = discord.Embed(
            title="🎉 THANH TOÁN THÀNH CÔNG (ADMIN)",
            description="Admin đã xác nhận giao dịch!",
            color=discord.Color.green()
        )

        embed.add_field(name="📦 Sản phẩm", value=data["product"], inline=False)
        embed.add_field(name="💰 Số tiền", value=f"{data['price']:,} VND")
        embed.add_field(name="🧾 Mã đơn", value=order_code)
        embed.add_field(name="📥 Link tải", value=data["link"], inline=False)

        await channel.send(embed=embed)

        del bank_waiting[order_code]

        await ctx.send("✅ Đã xác nhận giao dịch thành công.")

    @commands.Cog.listener()
    async def on_message(self, message):

        if message.channel.id != BANK_CHANNEL_ID:
            return

        if message.author.bot is False:
            return

        content = message.content.strip()

        if len(content) < 6:
            return

        order_code = content[-6:].upper()

        if order_code not in bank_waiting:
            return

        data = bank_waiting[order_code]

        channel = self.bot.get_channel(data["channel"])

        embed = discord.Embed(
            title="🎉 THANH TOÁN THÀNH CÔNG",
            description="Đã xác nhận giao dịch!",
            color=discord.Color.green()
        )

        embed.add_field(name="📦 Sản phẩm", value=data["product"], inline=False)
        embed.add_field(name="💰 Số tiền", value=f"{data['price']:,} VND")
        embed.add_field(name="🧾 Mã đơn", value=order_code)
        embed.add_field(name="📥 Link tải", value=data["link"], inline=False)

        await channel.send(embed=embed)

        del bank_waiting[order_code]


async def setup(bot):
    await bot.add_cog(SellSystem(bot))

