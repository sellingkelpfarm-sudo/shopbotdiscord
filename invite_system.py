import discord
from discord.ext import commands
import sqlite3
import random
import string
import asyncio
import sys

# Khởi tạo Database Voucher
def init_db():
    conn = sqlite3.connect('vouchers.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS vouchers 
                 (user_id INTEGER, code TEXT, percent INTEGER, used INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

init_db()

class InviteSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def generate_voucher(self):
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

    @commands.command(name="voucher")
    async def use_voucher(self, ctx, code: str):
        # Chỉ áp dụng cho kênh ticket ngân hàng
        if "-" not in ctx.channel.name: return

        user_id = ctx.author.id
        code = code.upper()
        
        conn = sqlite3.connect('vouchers.db')
        c = conn.cursor()
        c.execute("SELECT rowid, percent FROM vouchers WHERE user_id = ? AND code = ? AND used = 0", (user_id, code))
        row = c.fetchone()

        if row:
            row_id, percent = row
            order_code = ctx.channel.name.split("-")[0].upper()

            # LẤY MODULE SELL_SYSTEM ĐANG CHẠY TRONG BỘ NHỚ
            sell_mod = sys.modules.get('sell_system')
            if not sell_mod:
                # Thử tìm với tên file bạn đã đặt
                sell_mod = sys.modules.get('sell_system (1)')

            if sell_mod and order_code in sell_mod.bank_waiting:
                old_price = sell_mod.bank_waiting[order_code]['price']
                new_price = int(old_price * (1 - percent / 100))

                # 1. Cập nhật giá mới vào bộ nhớ sell_system
                sell_mod.bank_waiting[order_code]['price'] = new_price
                
                # 2. Xóa lệnh !voucher khách vừa gõ
                try: await ctx.message.delete()
                except: pass

                # 3. Tìm và sửa Embed gốc trong kênh thành "Đã giảm giá"
                async for message in ctx.channel.history(limit=20):
                    if message.author == self.bot.user and len(message.embeds) > 0:
                        embed = message.embeds[0]
                        if "XÁC NHẬN THANH TOÁN" in (embed.title or ""):
                            # Trang trí lại Embed
                            new_desc = embed.description.replace(f"{old_price:,} VND", f"~~{old_price:,}~~ -> **{new_price:,} VND**")
                            embed.description = new_desc + f"\n\n✨ **VOUCHER GIẢM {percent}% ĐÃ ÁP DỤNG!**"
                            embed.color = 0xf1c40f # Màu vàng Gold
                            await message.edit(embed=embed)
                            break
                
                c.execute("UPDATE vouchers SET used = 1 WHERE rowid = ?", (row_id,))
                conn.commit()
                await ctx.send(f"✅ Đã dùng mã giảm **{percent}%**. Vui lòng thanh toán số tiền mới!", delete_after=10)
            else:
                await ctx.send("❌ Không tìm thấy đơn hàng hoặc hệ thống chưa tải xong.", delete_after=5)
        else:
            await ctx.send("❌ Mã voucher không đúng hoặc đã dùng.", delete_after=5)
        conn.close()

    # Hàm tặng mã khi thanh toán thành công (Tính % theo giá trị đơn)
    async def give_voucher_logic(self, user, product_name, amount, guild):
        # Mua dưới 100k giảm 10%, Trên 100k giảm 50% (Tối đa)
        if amount >= 100000: percent = 50
        else: percent = 10
            
        new_code = self.generate_voucher()
        conn = sqlite3.connect('vouchers.db')
        conn.execute("INSERT INTO vouchers VALUES (?, ?, ?, 0)", (user.id, new_code, percent))
        conn.commit()
        conn.close()

        # Embed DM trang trí cực đẹp
        embed = discord.Embed(
            title="🎊 THANH TOÁN THÀNH CÔNG 🎊",
            description=(
                f"CHÚC MỪNG BẠN ĐÃ THANH TOÁN THÀNH CÔNG ĐƠN HÀNG **{product_name}**\n"
                f"VỚI SỐ TIỀN **{amount:,} VND**.\n\n"
                f"🎁 BẠN ĐÃ NHẬN ĐƯỢC MÃ GIẢM GIÁ GIẢM **{percent}%** CHO ĐƠN HÀNG TIẾP THEO.\n"
                f"🎫 MÃ VOUCHER: **{new_code}**\n\n"

                f"*Dùng lệnh !voucher **{new_code}** trong đơn hàng tiếp theo của bạn để được giảm **{percent}%** nhé!*"

                f"**CẢM ƠN BẠN VÌ ĐÃ TIN TƯỞNG VÀ SỬ DỤNG DỊCH VỤ CỦA LOTUSS'S SCHEMATIC SHOP!**"
            ),
            color=0x2ecc71
        )
        if guild.icon: embed.set_thumbnail(url=guild.icon.url)
        embed.set_footer(text="LoTuss's Shop • Uy tín - Chất lượng")
        try: await user.send(embed=embed)
        except: pass

async def setup(bot):
    await bot.add_cog(InviteSystem(bot))