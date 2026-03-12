import discord
from discord.ext import commands, tasks
import sqlite3
import random
import string
import asyncio
import os
from datetime import datetime, timedelta

# ===== KHỞI TẠO DATABASE =====
def init_db():
    conn = sqlite3.connect('bank_orders.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS vouchers 
                 (user_id INTEGER, code TEXT, percent INTEGER, used INTEGER DEFAULT 0, expiry_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admin_vouchers 
                 (code TEXT PRIMARY KEY, percent INTEGER, max_uses INTEGER, 
                  current_uses INTEGER DEFAULT 0, expiry_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS leaderboard 
                 (user_id INTEGER PRIMARY KEY, total_spent INTEGER DEFAULT 0, order_count INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS affiliate_rewards 
                 (inviter_id INTEGER, invited_id INTEGER, rewarded INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

init_db()

class InviteSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.invites = {}
        if not self.update_top_task.is_running():
            self.update_top_task.start()

    def cog_unload(self):
        self.update_top_task.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            try: 
                self.invites[guild.id] = await guild.invites()
            except: 
                pass

    @commands.command(name="createvoucher")
    @commands.has_permissions(administrator=True)
    async def createvoucher(self, ctx, code: str, percent: int, max_uses: int, days: int):
        code = code.upper()
        expiry_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        conn = sqlite3.connect('bank_orders.db')
        try:
            conn.execute("INSERT INTO admin_vouchers (code, percent, max_uses, expiry_date) VALUES (?, ?, ?, ?)",
                         (code, percent, max_uses, expiry_date))
            conn.commit()
            await ctx.send(f"✅ Đã tạo Voucher chung: `{code}` giảm **{percent}%**, lượt dùng: **{max_uses}**, hạn: **{days} ngày**.")
        except sqlite3.IntegrityError:
            await ctx.send("❌ Mã Voucher này đã tồn tại!")
        finally:
            conn.close()

    def generate_voucher(self):
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

    async def get_inviter(self, member):
        try:
            new_invites = await member.guild.invites()
            old_invites = self.invites.get(member.guild.id, [])
            self.invites[member.guild.id] = new_invites
            for invite in old_invites:
                for new_invite in new_invites:
                    if invite.code == new_invite.code and invite.uses < new_invite.uses:
                        return invite.inviter
        except: 
            return None

    # --- HÀM XỬ LÝ VOUCHER KHI NGƯỜI DÙNG NHẬP MÃ ---
    async def process_voucher_logic(self, interaction, code, order_code):
        import sell_system # Import tại đây để tránh vòng lặp import (Circular Import)
        code = code.upper()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn = sqlite3.connect('bank_orders.db')
        c = conn.cursor()
        
        # 1. Kiểm tra mã admin tạo
        c.execute("SELECT percent, max_uses, current_uses FROM admin_vouchers WHERE code = ? AND expiry_date > ?", (code, now))
        res = c.fetchone()
        
        # 2. Nếu không có, kiểm tra mã cá nhân (mã tặng lần đầu)
        if not res:
            c.execute("SELECT percent, used FROM vouchers WHERE user_id = ? AND code = ? AND expiry_date > ? AND used = 0", 
                      (interaction.user.id, code, now))
            res_personal = c.fetchone()
            if res_personal:
                percent = res_personal[0]
                if order_code in sell_system.bank_waiting:
                    old_price = sell_system.bank_waiting[order_code]['price']
                    new_price = int(old_price * (1 - percent/100))
                    sell_system.bank_waiting[order_code]['price'] = new_price
                    # Đánh dấu đã sử dụng mã cá nhân
                    conn.execute("UPDATE vouchers SET used = 1 WHERE user_id = ? AND code = ?", (interaction.user.id, code))
                    conn.commit()
                    conn.close()
                    return percent, new_price

        # 3. Xử lý nếu là mã admin
        if res and res[2] < res[1]:
            percent = res[0]
            if order_code in sell_system.bank_waiting:
                old_price = sell_system.bank_waiting[order_code]['price']
                new_price = int(old_price * (1 - percent/100))
                sell_system.bank_waiting[order_code]['price'] = new_price
                conn.execute("UPDATE admin_vouchers SET current_uses = current_uses + 1 WHERE code = ?", (code,))
                conn.commit()
                conn.close()
                return percent, new_price
        
        conn.close()
        return None, None

    # --- HÀM TẶNG VOUCHER & CẬP NHẬT BXH ---
    async def give_voucher_logic(self, member, product_name, amount, guild):
        conn = sqlite3.connect('bank_orders.db')
        c = conn.cursor()
        user_id = member.id
        
        c.execute("SELECT order_count FROM leaderboard WHERE user_id = ?", (user_id,))
        res = c.fetchone()
        old_order_count = res[0] if res else 0

        # Cập nhật Leaderboard
        conn.execute("INSERT INTO leaderboard (user_id, total_spent, order_count) VALUES (?, ?, 1) "
                     "ON CONFLICT(user_id) DO UPDATE SET total_spent = total_spent + ?, order_count = order_count + 1",
                     (user_id, amount, amount))
        conn.commit()

        # Tặng mã 20% cho đơn ĐẦU TIÊN
        if old_order_count == 0:
            voucher_code = self.generate_voucher()
            expiry_str = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
            
            conn.execute("INSERT INTO vouchers (user_id, code, percent, used, expiry_date) VALUES (?, ?, ?, 0, ?)", 
                         (user_id, voucher_code, 20, expiry_str))
            conn.commit()

            try:
                embed = discord.Embed(title="🎁 QUÀ TẶNG LẦN ĐẦU MUA HÀNG", color=0x2ecc71)
                embed.description = f"Cảm ơn bạn đã tin dùng dịch vụ của ***LoTuss's Shop***!\nVì đây là đơn hàng đầu tiên, shop tặng bạn 1 mã giảm giá 20% cho lần sau."
                embed.add_field(name="🎫 Mã Voucher", value=f"`{voucher_code}`", inline=True)
                embed.add_field(name="📉 Giảm giá", value="**20%**", inline=True)
                embed.add_field(name="⏰ Hạn dùng", value="7 Ngày", inline=True)
                embed.set_footer(text="Nhấn 'NHẬP VOUCHER' trong đơn hàng tới để áp dụng nhé!")
                await member.send(embed=embed)
            except:
                pass
        
        conn.close()

    @tasks.loop(hours=1)
    async def update_top_task(self):
        await self.bot.wait_until_ready()
        conn = sqlite3.connect('bank_orders.db')
        c = conn.cursor()
        c.execute("SELECT value FROM config WHERE key = 'top_channel'")
        ch_id = c.fetchone()
        if not ch_id: 
            return
        
        c.execute("SELECT user_id, total_spent FROM leaderboard ORDER BY total_spent DESC LIMIT 10")
        rows = c.fetchall()
        
        embed = discord.Embed(title="🏆 TOP ĐẠI GIA - CHI TIÊU NHIỀU NHẤT", color=0xffd700)
        desc = ""
        for i, r in enumerate(rows):
            desc += f"#{i+1} <@{r[0]}> - `{r[1]:,} VND`\n"
        embed.description = desc or "Chưa có dữ liệu."
        
        channel = self.bot.get_channel(ch_id[0])
        if channel: 
            await channel.send(embed=embed)
        conn.close()

    @commands.command(name="settop")
    @commands.has_permissions(administrator=True)
    async def settop(self, ctx):
        conn = sqlite3.connect('bank_orders.db')
        conn.execute("INSERT OR REPLACE INTO config VALUES ('top_channel', ?)", (ctx.channel.id,))
        conn.commit()
        conn.close()
        await ctx.send("✅ Đã thiết lập kênh BXH.")

async def setup(bot):
    await bot.add_cog(InviteSystem(bot))
