import discord
from discord.ext import commands
import random
import string
import time
import asyncio

cooldowns = {}

# ======================
# BANK STORAGE
# ======================

bank_waiting = {}

# ======================

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

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ CÓ", style=discord.ButtonStyle.red, custom_id="confirm_cancel")
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.send_message("⏳ Kênh sẽ bị xoá sau 5 giây.")

        await asyncio.sleep(5)

        await interaction.channel.delete()

    @discord.ui.button(label="❌ KHÔNG", style=discord.ButtonStyle.green, custom_id="deny_cancel")
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

    @discord.ui.button(
        label="💳 CHUYỂN KHOẢN",
        style=discord.ButtonStyle.green,
        custom_id="pay_bank"
    )
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

    @discord.ui.button(
        label="❌ HỦY ĐƠN",
        style=discord.ButtonStyle.red,
        custom_id="cancel_order"
    )
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

    @discord.ui.button(
        label="🛒 MUA NGAY",
        style=discord.ButtonStyle.green,
        custom_id="buy_product"
    )
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

        # đăng ký persistent view để bot restart vẫn bấm được
        bot.add_view(BuyView(0, "product", "link"))
        bot.add_view(PaymentView(0, "product", "link", "code"))
        bot.add_view(CancelConfirm())

    @commands.command()
    async def sell(self, ctx, bank_price: int, link: str):

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

    @commands.command()
    async def dabank(self, ctx, order_code: str):

        if order_code not in bank_waiting:
            await ctx.send("❌ Không tìm thấy đơn.")
            return

        data = bank_waiting[order_code]

        embed = discord.Embed(
            title="🎉 THANH TOÁN THÀNH CÔNG",
            description="Cảm ơn bạn đã mua hàng!",
            color=discord.Color.green()
        )

        embed.add_field(
            name="📦 Sản phẩm",
            value=data["product"],
            inline=False
        )

        embed.add_field(
            name="💰 Số tiền",
            value=f"{data['price']:,} VND",
            inline=True
        )

        embed.add_field(
            name="🧾 Mã đơn",
            value=order_code,
            inline=True
        )

        embed.add_field(
            name="💬 Nội dung CK",
            value=f"`{order_code}`",
            inline=False
        )

        embed.add_field(
            name="📥 Link tải",
            value=data["link"],
            inline=False
        )

        embed.set_footer(text="Cảm ơn bạn đã mua hàng ❤️")
        embed.set_footer(text="Nếu có sự cố gì thì cứ nhắn tin ở đây để được giải quyết nhé!!^w^")

        await ctx.send(embed=embed)

        del bank_waiting[order_code]


async def setup(bot):
    await bot.add_cog(SellSystem(bot))
