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
        self.update_top_task.start()

    def cog_unload(self):
        self.update_top_task.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            try: self.invites[guild.id] = await guild.invites()
            except: pass

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
        except: return None

    # --- HÀM QUAN TRỌNG: XỬ LÝ TẶNG VOUCHER & LEADERBOARD ---
    async def give_voucher_logic(self, member, product_name, amount, guild):
        conn = sqlite3.connect('bank_orders.db')
        c = conn.cursor()
        user_id = member.id
        
        # Lấy số đơn hàng cũ trước khi cập nhật
        c.execute("SELECT order_count FROM leaderboard WHERE user_id = ?", (user_id,))
        res = c.fetchone()
        old_order_count = res[0] if res else 0

        # Cập nhật Leaderboard
        conn.execute("INSERT INTO leaderboard (user_id, total_spent, order_count) VALUES (?, ?, 1) "
                     "ON CONFLICT(user_id) DO UPDATE SET total_spent = total_spent + ?, order_count = order_count + 1",
                     (user_id, amount, amount))
        conn.commit()

        # Nếu là đơn hàng ĐẦU TIÊN (old_order_count == 0), tặng voucher 20%
        if old_order_count == 0:
            voucher_code = self.generate_voucher()
            expiry_str = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
            
            conn.execute("INSERT INTO vouchers (user_id, code, percent, used, expiry_date) VALUES (?, ?, ?, 0, ?)", 
                         (user_id, voucher_code, 20, expiry_str))
            conn.commit()

            try:
                embed = discord.Embed(title="🎁 QUÀ TẶNG LẦN ĐẦU MUA HÀNG", color=0x2ecc71)
                embed.description = f"Cảm ơn bạn đã tin dùng dịch vụ! Vì đây là đơn hàng đầu tiên, shop tặng bạn 1 mã giảm giá cho lần sau."
                embed.add_field(name="🎫 Mã Voucher (Giảm 20%)", value=f"`{voucher_code}`", inline=False)
                embed.add_field(name="⏰ Hạn dùng", value="7 Ngày", inline=True)
                embed.set_footer(text="Sử dụng mã này trong lần mua tới nhé!")
                await member.send(embed=embed)
            except:
                pass
        
        conn.close()

    @tasks.loop(hours=1)
    async def update_top_task(self):
        # (Giữ nguyên logic update_top của bạn)
        pass

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
