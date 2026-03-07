import discord
from discord.ext import commands
import requests
import random
import string
import time

API_KEY = "YOUR_API_KEY"

cooldowns = {}


def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


def anti_spam(user_id):

    now = time.time()

    if user_id in cooldowns:
        if now - cooldowns[user_id] < 10:
            return False

    cooldowns[user_id] = now
    return True


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

        url = "https://napthe.vn/api/card"

        data = {
            "APIKey": API_KEY,
            "Network": self.telco.value,
            "CardValue": self.price,
            "CardSeri": self.serial.value,
            "CardCode": self.code.value,
            "RequestId": self.order_id
        }

        try:

            res = requests.post(url, json=data).json()

            if res.get("status") == 1:

                embed = discord.Embed(
                    title="✅ THANH TOÁN THÀNH CÔNG",
                    description=f"📥 Link tải:\n{self.link}",
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

        except Exception as e:

            embed = discord.Embed(
                title="❌ LỖI API",
                description="Không thể kết nối API.",
                color=discord.Color.red()
            )

            await interaction.followup.send(embed=embed)


class PaymentView(discord.ui.View):

    def __init__(self, bank_price, card_price, product, link):
        super().__init__(timeout=None)

        self.bank_price = bank_price
        self.card_price = card_price
        self.product = product
        self.link = link
        self.code = generate_code()

    @discord.ui.button(label="💳 Chuyển khoản", style=discord.ButtonStyle.green)
    async def bank(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not anti_spam(interaction.user.id):

            await interaction.response.send_message(
                "⏳ Bạn thao tác quá nhanh, vui lòng đợi.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="💳 THANH TOÁN CHUYỂN KHOẢN",
            description=(
                f"📦 **Sản phẩm:** {self.product}\n"
                f"💰 **Số tiền cần thanh toán:** {self.bank_price:,} VND\n"
                f"🧾 **Mã đơn hàng:** {self.code}\n\n"
                "⚠ **Lưu ý:**\n"
                f"• Nội dung chuyển khoản: **DH_{self.code}**\n"
                "• Chuyển khoản đúng số tiền\n"
                "• Sai nội dung thì sẽ không hoàn tiền lại.\n\n"
                "Sau khi thanh toán vui lòng chờ admin xác nhận thủ công^w^."
            ),
            color=discord.Color.green()
        )

        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="🎴 Nạp thẻ", style=discord.ButtonStyle.blurple)
    async def card(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not anti_spam(interaction.user.id):

            await interaction.response.send_message(
                "⏳ Bạn thao tác quá nhanh, vui lòng đợi.",
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


class SellSystem(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def sell(self, ctx, bank_price: int, card_price: int, product: str, link: str):

        embed = discord.Embed(
            title="🛒 MUA SẢN PHẨM",
            description=(
                f"📦 **Sản phẩm:** {product}\n\n"
                f"💳 Chuyển khoản: {bank_price:,} VND\n"
                f"🎴 Nạp card: {card_price:,} VND\n\n"
                "Chọn phương thức thanh toán bên dưới."
            ),
            color=discord.Color.blue()
        )

        await ctx.send(
            embed=embed,
            view=PaymentView(bank_price, card_price, product, link)
        )


async def setup(bot):
    await bot.add_cog(SellSystem(bot))
