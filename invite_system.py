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

    # --- LỆNH TẠO VOUCHER ADMIN (Lệnh bạn đang thiếu) ---
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

    # --- LỆNH CÀI ĐẶT KÊNH WELCOME ---
    @commands.command(name="setwelcome")
    @commands.has_permissions(administrator=True)
    async def setwelcome(self, ctx):
        conn = sqlite3.connect('bank_orders.db')
        conn.execute("INSERT OR REPLACE INTO config VALUES ('welcome_channel', ?)", (ctx.channel.id,))
        conn.commit()
        conn.close()
        await ctx.send(f"✅ Đã thiết lập kênh {ctx.channel.mention} làm nơi gửi thông báo chào mừng.")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild = member.guild
        inviter = await self.get_inviter(member)
        conn = sqlite3.connect('bank_orders.db')
        c = conn.cursor()
        c.execute("SELECT value FROM config WHERE key = 'welcome_channel'")
        res = c.fetchone()
        conn.close()

        if res:
            channel = self.bot.get_channel(res[0])
            if channel:
                embed = discord.Embed(title="✨ THÀNH VIÊN MỚI", description=f"Chào mừng {member.mention}!", color=discord.Color.blue())
                embed.add_field(name="👤 Người mời", value=f"{inviter.mention if inviter else 'Không rõ'}")
                embed.set_thumbnail(url=member.display_avatar.url)
                await channel.send(embed=embed)

    @tasks.loop(hours=1)
    async def update_top_task(self):
        await self.bot.wait_until_ready()
        conn = sqlite3.connect('bank_orders.db')
        c = conn.cursor()
        c.execute("SELECT value FROM config WHERE key = 'top_channel'")
        ch_id = c.fetchone()
        if not ch_id: return
        
        c.execute("SELECT user_id, total_spent FROM leaderboard ORDER BY total_spent DESC LIMIT 10")
        rows = c.fetchall()
        embed = discord.Embed(title="🏆 TOP ĐẠI GIA", color=0xffd700)
        desc = ""
        for i, r in enumerate(rows):
            desc += f"#{i+1} <@{r[0]}> - `{r[1]:,} VND`\n"
        embed.description = desc or "Chưa có dữ liệu."
        
        channel = self.bot.get_channel(ch_id[0])
        if channel: await channel.send(embed=embed)
        conn.close()

    @commands.command(name="settop")
    @commands.has_permissions(administrator=True)
    async def settop(self, ctx):
        conn = sqlite3.connect('bank_orders.db')
        conn.execute("INSERT OR REPLACE INTO config VALUES ('top_channel', ?)", (ctx.channel.id,))
        conn.commit()
        conn.close()
        await ctx.send("✅ Đã thiết lập kênh BXH.")

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

    async def process_voucher_logic(self, interaction, code, order_code):
        import sell_system
        code = code.upper()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn = sqlite3.connect('bank_orders.db')
        c = conn.cursor()
        
        # Check admin voucher
        c.execute("SELECT percent, max_uses, current_uses FROM admin_vouchers WHERE code = ? AND expiry_date > ?", (code, now))
        res = c.fetchone()
        if res and res[2] < res[1]:
            percent = res[0]
            # Cập nhật giá bên sell_system
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

async def setup(bot):
    await bot.add_cog(InviteSystem(bot))
