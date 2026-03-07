import discord
from discord.ext import commands


class ShopView(discord.ui.View):

    @discord.ui.button(label="Vào Shop", style=discord.ButtonStyle.primary)
    async def vao_shop(self, interaction: discord.Interaction, button: discord.ui.Button):

        role = interaction.guild.get_role(1479548161830686783)

        if role:
            await interaction.user.add_roles(role)

        await interaction.response.send_message(
            "Bạn đã vào khu Shopping!",
            ephemeral=True
        )

    @discord.ui.button(label="Thuê Build", style=discord.ButtonStyle.danger)
    async def thue_build(self, interaction: discord.Interaction, button: discord.ui.Button):

        role = interaction.guild.get_role(1479707478873866261)

        if role:
            await interaction.user.add_roles(role)

        await interaction.response.send_message(
            "Bạn đã vào khu Thuê Build!",
            ephemeral=True
        )


class MenuRole(commands.Cog):

    def __init__(self, bot):
        self.bot = bot


    @commands.command()
    async def shop(self, ctx):

        embed = discord.Embed(
            description=
            "🛒 **CHÀO MỪNG ĐẾN VỚI Lotuss's SCHEMATICS SHOP**\n\n"
            "⭐ Nơi cung cấp **Minecraft Farm Schematic** chất lượng cao\n"
            "⚡ Tối ưu cho **Survival • SMP • Skyblock**\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📦 **Dịch vụ tại Shop:**\n"
            "🌿 Farm tài nguyên tự động\n"
            "👾 Mob / XP Farm\n"
            "⚡ Redstone & Automatic Farm\n"
            "🏗 Thuê Builder build trực tiếp\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🛒 **Vào Shop** → Xem danh sách schematic\n"
            "🏗 **Thuê Build** → Thuê builder build farm\n"
            "💬 Nếu cần hỗ trợ hãy liên hệ **Staff**",
            color=discord.Color.green()
        )

        await ctx.send(
            embed=embed,
            view=ShopView()
        )


async def setup(bot):
    await bot.add_cog(MenuRole(bot))
