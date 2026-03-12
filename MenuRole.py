import discord
from discord.ext import commands

class ShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🛒 VÀO SHOP",
        style=discord.ButtonStyle.primary,
        custom_id="menu_shop"
    )
    async def vao_shop(self, interaction: discord.Interaction, button: discord.ui.Button):
        role_id = 1479548161830686783
        role = interaction.guild.get_role(role_id)

        if role:
            if role in interaction.user.roles:
                await interaction.response.send_message(
                    "✨ **BẠN ĐÃ CÓ ROLE SHOPPING RỒI!** ✨\n*Hãy kiểm tra các kênh bán hàng bên dưới nhé!*", 
                    ephemeral=True
                )
            else:
                await interaction.user.add_roles(role)
                await interaction.response.send_message(
                    "✅ **XÁC NHẬN:** Bạn đã vào khu **SHOPPING** thành công! 🛒",
                    ephemeral=True
                )
        else:
            await interaction.response.send_message("❌ Lỗi: Không tìm thấy Role Shop trên máy chủ.", ephemeral=True)

    @discord.ui.button(
        label="🏗️ THUÊ BUILD",
        style=discord.ButtonStyle.danger,
        custom_id="menu_build"
    )
    async def thue_build(self, interaction: discord.Interaction, button: discord.ui.Button):
        role_id = 1479707478873866261
        role = interaction.guild.get_role(role_id)

        if role:
            if role in interaction.user.roles:
                await interaction.response.send_message(
                    "✨ **BẠN ĐÃ CÓ ROLE BUILDING RỒI!** ✨\n*Hãy liên hệ với đội ngũ Builder để bắt đầu dự án.*", 
                    ephemeral=True
                )
            else:
                await interaction.user.add_roles(role)
                await interaction.response.send_message(
                    "✅ **XÁC NHẬN:** Bạn đã vào khu **BUILDING** thành công! 🏗️",
                    ephemeral=True
                )
        else:
            await interaction.response.send_message("❌ Lỗi: Không tìm thấy Role Build trên máy chủ.", ephemeral=True)


class MenuRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # Đảm bảo view luôn hoạt động kể cả khi bot khởi động lại (Persistent View)
        self.bot.add_view(ShopView())
        print("✅ MenuRole Persistent View đã được kích hoạt.")

    @commands.command(name="shop")
    @commands.has_permissions(administrator=True)
    async def shop(self, ctx):
        # Giữ nguyên Embed cũ của bạn theo yêu cầu
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
