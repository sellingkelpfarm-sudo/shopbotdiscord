import discord
from discord.ext import commands


def setup_menu(bot):

    class ShopView(discord.ui.View):

        @discord.ui.button(label="Vào Shop", style=discord.ButtonStyle.primary)
        async def vao_shop(self, interaction: discord.Interaction, button: discord.ui.Button):
            role = interaction.guild.get_role(1479548161830686783)
            await interaction.user.add_roles(role)
            await interaction.response.send_message("Bạn đã vào khu Shopping!", ephemeral=True)

        @discord.ui.button(label="Thuê Build", style=discord.ButtonStyle.danger)
        async def thue_build(self, interaction: discord.Interaction, button: discord.ui.Button):
            role = interaction.guild.get_role(1479707478873866261)
            await interaction.user.add_roles(role)
            await interaction.response.send_message("Bạn đã vào khu Building!", ephemeral=True)


    @bot.command()
    async def shop(ctx):

        embed = discord.Embed(
            description=
            "🏪 **CHÀO MỪNG ĐẾN VỚI LoTuss's SCHEMATICS SHOP**\n\n"
            "✨ Nơi cung cấp **Minecraft Farm Schematic** chất lượng cao\n"
            "⚡ Tối ưu cho **Survival • SMP • Skyblock**\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📦 **Dịch vụ tại Shop:**\n"
            "🌾 Farm tài nguyên tự động\n"
            "🧟 Mob / XP Farm\n"
            "⚡ Redstone & Automatic Farm\n"
            "🏗️ Thuê Builder build trực tiếp\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "🛒 **Vào Shop** → Xem danh sách schematic\n"
            "🔨 **Thuê Build** → Thuê builder build farm\n\n"
            "💬 Nếu cần hỗ trợ hãy liên hệ **Staff**"
        )


        await ctx.send(embed=embed, view=ShopView())

