import discord
from discord.ext import commands
import random
import string
import time
import asyncio

cooldowns = {}
buy_cooldowns = {}
bank_waiting = {}
order_activity = {}

# ADD: giới hạn số đơn mỗi user
user_orders = {}

BANK_CHANNEL_ID = 1479440469120389221

# ADD: kênh thông báo thanh toán
PAYMENT_LOG_CHANNEL_ID = 1481239066115571885

# ADD: role đã thanh toán
PAID_ROLE_ID = 1479550698982215852

ORDER_TIMEOUT = 900


def generate_code():
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if code not in bank_waiting:
            return code


def anti_spam(user_id):
    now = time.time()

    if user_id in cooldowns:
        if now - cooldowns[user_id] < 10:
            return False

    cooldowns[user_id] = now
    return True


def anti_spam_buy(user_id):
    now = time.time()

    if user_id in buy_cooldowns:
        if now - buy_cooldowns[user_id] < 10:
            return False

    buy_cooldowns[user_id] = now
    return True


# ADD: tự xoá role sau 3 ngày
async def remove_role_later(member, role):
    await asyncio.sleep(259200)
    try:
        await member.remove_roles(role)
    except:
        pass


# ======================
# AUTO CLOSE CHANNEL (FIX)
# ======================

async def auto_close_channel(channel, order_code, user_id):

    await asyncio.sleep(ORDER_TIMEOUT)

    if order_code not in order_activity:
        return

    if order_activity[order_code]:
        return

    try:
        await channel.send("⌛ Đơn hàng đã bị đóng do không thanh toán trong 15 phút.")
        await asyncio.sleep(5)
        await channel.delete()
    except:
        pass

    if order_code in order_activity:
        del order_activity[order_code]

    if user_id in user_orders:
        user_orders[user_id] -= 1
        if user_orders[user_id] <= 0:
            del user_orders[user_id]


class CancelConfirm(discord.ui.View):

    @discord.ui.button(label="✅ CÓ", style=discord.ButtonStyle.red)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):

        user_id = interaction.user.id

        await interaction.response.send_message("⏳ Kênh sẽ bị xoá sau 5 giây.")

        await asyncio.sleep(5)

        try:
            await interaction.channel.delete()
        except:
            pass

        if user_id in user_orders:
            user_orders[user_id] -= 1
            if user_orders[user_id] <= 0:
                del user_orders[user_id]

    @discord.ui.button(label="❌ KHÔNG", style=discord.ButtonStyle.green)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.send_message(
            "👍 Đơn hàng vẫn được giữ.",
            ephemeral=True
        )


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

        order_activity[self.code] = True
        if self.code in order_activity:
            del order_activity[self.code]

        qr = f"https://img.vietqr.io/image/MB-0764495919-compact2.png?amount={self.bank_price}&addInfo={self.code}"

        embed = discord.Embed(
            title="💳 THANH TOÁN CHUYỂN KHOẢN",
            description=(
                f"📦 **Sản phẩm:** {self.product}\n"
                f"💰 **Số tiền:** {self.bank_price:,} VND\n"
                f"🧾 **Mã đơn:** {self.code}\n\n"
                f"📥 **Nội dung CK:** `{self.code}`\n"
                f"#lưu ý: nội dung chuyển khoản không được chỉnh sửa! | "
                f"Và vui lòng chụp bill thanh toán rõ lên trên này nếu gặp lỗi thì admin sẽ giải quyết sớm!"
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
            "price": self.bank_price,
            "user": interaction.user.id
        }

        asyncio.create_task(bank_countdown(msg, self.code))

    @discord.ui.button(label="❌ HỦY ĐƠN", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):

        embed = discord.Embed(
            title="⚠ XÁC NHẬN HỦY ĐƠN",
            description="BẠN CÓ CHẮC HỦY ĐƠN HÀNG CHỨ?",
            color=discord.Color.orange()
        )

        await interaction.response.send_message(
            embed=embed,
            view=CancelConfirm()
        )


class BuyView(discord.ui.View):

    def __init__(self, bank_price, product, link):

        super().__init__(timeout=None)

        self.bank_price = bank_price
        self.product = product
        self.link = link

    @discord.ui.button(label="🛒 MUA NGAY", style=discord.ButtonStyle.green)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):

        user_id = interaction.user.id

        if not anti_spam_buy(user_id):

            await interaction.response.send_message(
                "⏳ Bạn đang tạo đơn quá nhanh. Vui lòng đợi vài giây.",
                ephemeral=True
            )
            return

        if user_id in user_orders and user_orders[user_id] >= 3:
            await interaction.response.send_message(
                "🚫 Bạn đã đạt giới hạn 3 đơn hàng đang mở. Hãy hoàn thành hoặc hủy đơn trước.",
                ephemeral=True
            )
            return

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

        user_orders[user_id] = user_orders.get(user_id, 0) + 1

        embed = discord.Embed(
            title="# 💳 XÁC NHẬN THANH TOÁN BẰNG NGÂN HÀNG",
            description=(
                f"📦 **Tên hàng:** {self.product}\n"
                f"💰 **Số tiền:** {self.bank_price:,} VND\n"
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

        order_activity[order_code] = False

        asyncio.create_task(
            auto_close_channel(channel, order_code, user_id)
        )

        await interaction.response.send_message(
            f"✅ Đơn hàng đã tạo: {channel.mention}",
            ephemeral=True
        )


class SellSystem(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="sellbank")
    async def sellbank(self, ctx, bank_price: int, link: str):

        product = ctx.channel.name

        embed = discord.Embed(
            title="🛒 THANH TOÁN BẰNG CÁCH CHUYỂN KHOẢN NGÂN HÀNG",
            description=(
                f"📦 **Tên hàng:** {product}\n\n"
                f"💳 **Số tiền**: {bank_price:,} VND\n\n"
                "👇 **Nhấn nút MUA NGAY bên dưới để bắt đầu thanh toán**"
            ),
            color=discord.Color.blue()
        )

        await ctx.send(
            embed=embed,
            view=BuyView(bank_price, product, link)
        )

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

        embed.add_field(name="📦 Tên hàng", value=data["product"], inline=False)
        embed.add_field(name="💰 Số tiền", value=f"{data['price']:,} VND")
        embed.add_field(name="🧾 Mã đơn", value=order_code)
        embed.add_field(name="📥 Link tải", value=data["link"], inline=False)

        await channel.send(embed=embed)

        guild = channel.guild
        member = guild.get_member(data["user"])

        log_channel = self.bot.get_channel(PAYMENT_LOG_CHANNEL_ID)

        if log_channel and member:
            await log_channel.send(
                f"{member.mention} đã thanh toán đơn hàng **{data['product']}** với số tiền **{data['price']:,} VND**, Bạn đánh giá dịch vụ của chúng tớ tại #feed-back nhé!"
            )

        if member:
            role = guild.get_role(PAID_ROLE_ID)
            if role:
                await member.add_roles(role)
                asyncio.create_task(remove_role_later(member, role))

        del bank_waiting[order_code]


async def setup(bot):
    await bot.add_cog(SellSystem(bot))
