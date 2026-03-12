import discord
from discord.ext import commands, tasks
import sqlite3
import random
import string
import asyncio
import sys
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

    # --- LỆNH CÀI ĐẶT KÊNH WELCOME ---
    @commands.command(name="setwelcome")
    @commands.has_permissions(administrator=True)
    async def setwelcome(self, ctx):
        conn = sqlite3.connect('bank_orders.db')
        conn.execute("INSERT OR REPLACE INTO config VALUES ('welcome_channel', ?)", (ctx.channel.id,))
        conn.commit()
        conn.close()
        await ctx.send(f"✅ Đã thiết lập kênh {ctx.channel.mention} làm nơi gửi thông báo chào mừng.")

    # --- EVENT CHÀO MỪNG THÀNH VIÊN ---
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
                embed = discord.Embed(
                    title="✨ THÀNH VIÊN MỚI GIA NHẬP",
                    description=f"Chào mừng {member.mention} đã đến với **LoTuss's Schematic Shop**!",
                    color=0x9b59b6
                )
                if inviter:
                    embed.add_field(name="👤 Người mời", value=f"{inviter.mention}", inline=True)
                    embed.set_footer(text=f"{inviter.display_name} đã mời thành công {member.display_name} vào Shop")
                else:
                    embed.add_field(name="👤 Người mời", value="Không rõ nguồn", inline=True)
                    embed.set_footer(text=f"Chào mừng thành viên thứ {len(guild.members)}")

                embed.set_thumbnail(url=member.display_avatar.url)
                if guild.icon: embed.set_author(name=guild.name, icon_url=guild.icon.url)
                
                await channel.send(content=member.mention, embed=embed)

    # --- CÁC LOGIC KHÁC GIỮ NGUYÊN ---
    @tasks.loop(hours=1)
    async def update_top_task(self):
        await self.bot.wait_until_ready()
        conn = sqlite3.connect('bank_orders.db')
        c = conn.cursor()
        c.execute("SELECT value FROM config WHERE key = 'top_channel'")
        ch_id = c.fetchone()
        c.execute("SELECT value FROM config WHERE key = 'top_message'")
        msg_id = c.fetchone()
        if not ch_id: 
            conn.close()
            return
        c.execute("SELECT user_id, total_spent FROM leaderboard ORDER BY total_spent DESC LIMIT 50")
        rows = c.fetchall()
        embed = discord.Embed(title="🏆 BẢNG XẾP HẠNG 50 ĐẠI GIA THANH TOÁN", color=0xffd700, description="Vinh danh những khách hàng thân thiết nhất của LoTuss's Shop! ❤️")
        if rows:
            leaderboard_text = ""
            for i, r in enumerate(rows):
                emoji = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"`#{i+1:02}`"
                leaderboard_text += f"{emoji} <@{r[0]}> — `{r[1]:,} VND`\n"
                if (i + 1) % 25 == 0:
                    embed.add_field(name=f"Top {i-23}-{i+1}", value=leaderboard_text, inline=False)
                    leaderboard_text = ""
            if leaderboard_text: embed.add_field(name=f"Danh sách tiếp theo", value=leaderboard_text, inline=False)
        else: embed.description = "Chưa có dữ liệu giao dịch nào."
        embed.set_footer(text=f"Cập nhật tự động: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}")
        channel = self.bot.get_channel(ch_id[0])
        if channel:
            try:
                if msg_id:
                    msg = await channel.fetch_message(msg_id[0])
                    await msg.edit(embed=embed)
                else:
                    new_msg = await channel.send(embed=embed)
                    c.execute("INSERT OR REPLACE INTO config VALUES ('top_message', ?)", (new_msg.id,))
                    conn.commit()
            except:
                new_msg = await channel.send(embed=embed)
                c.execute("INSERT OR REPLACE INTO config VALUES ('top_message', ?)", (new_msg.id,))
                conn.commit()
        conn.close()

    @commands.command(name="settop")
    @commands.has_permissions(administrator=True)
    async def settop(self, ctx):
        conn = sqlite3.connect('bank_orders.db')
        conn.execute("INSERT OR REPLACE INTO config VALUES ('top_channel', ?)", (ctx.channel.id,))
        conn.execute("DELETE FROM config WHERE key = 'top_message'")
        conn.commit()
        conn.close()
        await ctx.send(f"✅ Đã thiết lập kênh {ctx.channel.mention} làm nơi hiển thị Top 50.")
        await self.update_top_task()

    def generate_voucher(self):
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

    def count_active_vouchers(self, user_id):
        conn = sqlite3.connect('bank_orders.db')
        c = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        c.execute("SELECT COUNT(*) FROM vouchers WHERE user_id = ? AND used = 0 AND expiry_date > ?", (user_id, now))
        count = c.fetchone()[0]
        conn.close()
        return count

    async def give_voucher_logic(self, user, product_name, amount, guild):
        conn = sqlite3.connect('bank_orders.db')
        c = conn.cursor()
        expiry_str = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
        c.execute("SELECT order_count FROM leaderboard WHERE user_id = ?", (user.id,))
        res = c.fetchone()
        order_count = res[0] if res else 0
        conn.execute("INSERT INTO leaderboard (user_id, total_spent, order_count) VALUES (?, ?, 1) ON CONFLICT(user_id) DO UPDATE SET total_spent = total_spent + ?, order_count = order_count + ?", (user.id, amount, amount, 1))
        conn.commit()

        # Logic tặng voucher người mua
        should_give_buyer, percent_buyer = False, 10
        if order_count == 0: should_give_buyer, percent_buyer = True, 20
        else:
            luck = random.randint(1, 100)
            if amount < 50000: rate, percent_buyer = 10, random.randint(5, 15)
            elif amount < 200000: rate, percent_buyer = 25, random.randint(15, 30)
            else: rate, percent_buyer = 50, random.randint(30, 50)
            if luck <= rate: should_give_buyer = True

        if should_give_buyer and self.count_active_vouchers(user.id) < 3:
            code_b = self.generate_voucher()
            conn.execute("INSERT INTO vouchers (user_id, code, percent, used, expiry_date) VALUES (?, ?, ?, 0, ?)", (user.id, code_b, percent_buyer, expiry_str))
            conn.commit()
            try:
                embed_b = discord.Embed(title="🎁 QUÀ TẶNG VOUCHER MỚI", color=0x2ecc71, description="Cảm ơn bạn đã ủng hộ shop!")
                embed_b.add_field(name="🎫 Mã Voucher", value=f"`{code_b}`", inline=True)
                embed_b.add_field(name="📉 Giảm giá", value=f"**{percent_buyer}%**", inline=True)
                embed_b.add_field(name="⏰ Hạn dùng", value="7 Ngày", inline=True)
                embed_b.set_footer(text="Nhấn 'Áp dụng Voucher' khi thanh toán để sử dụng!")
                await user.send(embed=embed_b)
            except: pass

        # Logic tặng voucher người mời
        inviter = await self.get_inviter(user)
        if inviter and inviter.id != user.id:
            c.execute("SELECT rewarded FROM affiliate_rewards WHERE inviter_id = ? AND invited_id = ?", (inviter.id, user.id))
            if not c.fetchone() and order_count == 0:
                code_i = self.generate_voucher()
                conn.execute("INSERT INTO vouchers (user_id, code, percent, used, expiry_date) VALUES (?, ?, ?, 0, ?)", (inviter.id, code_i, 20, expiry_str))
                conn.execute("INSERT INTO affiliate_rewards (inviter_id, invited_id, rewarded) VALUES (?, ?, 1)", (inviter.id, user.id))
                conn.commit()
                try:
                    embed_i = discord.Embed(title="🎊 THƯỞNG GIỚI THIỆU THÀNH CÔNG", color=0xf1c40f)
                    embed_i.description = f"Người bạn bạn mời <@{user.id}> vừa thanh toán đơn hàng đầu tiên!"
                    embed_i.add_field(name="🎫 Voucher tặng bạn", value=f"`{code_i}`", inline=True)
                    embed_i.add_field(name="📉 Mức giảm", value="**20%**", inline=True)
                    embed_i.add_field(name="⏰ Hạn dùng", value="7 Ngày", inline=True)
                    embed_i.set_footer(text="Cảm ơn bạn đã giới thiệu thành viên mới cho LoTuss's Shop! ❤️")
                    if guild and guild.icon: embed_i.set_thumbnail(url=guild.icon.url)
                    await inviter.send(embed=embed_i)
                except: pass
        conn.close()

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

    # (Lệnh createvoucher và process_voucher_logic giữ nguyên như cũ)
    async def process_voucher_logic(self, interaction, code, order_code):
        # ... logic xử lý áp dụng voucher ...
        pass

async def setup(bot):
    await bot.add_cog(InviteSystem(bot))
