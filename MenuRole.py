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
            description="KÍNH CHÀO QUÝ KHÁCH ĐÃ ĐẾN VỚI LoTuss's Schematics Shop!\n"
                        "Vui lòng chọn hạng mục ở bên dưới để tiếp tục sử dụng dịch vụ."
        )

        await ctx.send(embed=embed, view=ShopView())