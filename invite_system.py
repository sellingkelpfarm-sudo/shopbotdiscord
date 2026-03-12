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
                    color=discord.Color.blue()
                )
                if inviter:
                    embed.add_field(name="👤 Người mời", value=f"{inviter.mention}", inline=True)
                    embed.set_footer(text=f"Mời thành công bởi {inviter.display_name}")
                else:
                    embed.add_field(name="👤 Người mời", value="`Không rõ nguồn`", inline=True)
                    embed.set_footer(text=f"Thành viên thứ {len(guild.members)} của Shop")

                embed.set_thumbnail(url=member.display_avatar.url)
                if guild.icon: embed.set_author(name=guild.name, icon_url=guild.icon.url)
                await channel.send(content=member.mention, embed=embed)

    # --- BẢNG XẾP HẠNG ---
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
        embed = discord.Embed(
            title="🏆 BẢNG XẾP HẠNG ĐẠI GIA", 
            color=0xffd700, 
            description="Vinh danh những khách hàng thân thiết nhất của LoTuss's Shop! ❤️"
        )
        
        if rows:
            leaderboard_text = ""
            for i, r in enumerate(rows):
                emoji = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"`#{i+1:02}`"
                leaderboard_text += f"{emoji} <@{r[0]}> — `{r[1]:,} VND`\n"
                if (i + 1) % 25 == 0:
                    embed.add_field(name=f"Top {i-23}-{i+1}", value=leaderboard_text, inline=False)
                    leaderboard_text = ""
            if leaderboard_text: embed.add_field(name=f"Danh sách tiếp theo", value=leaderboard_text, inline=False)
        else: 
            embed.description = "Chưa có dữ liệu giao dịch nào."
            
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

    # --- LOGIC TẶNG VOUCHER ---
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
                embed_b = discord.Embed(title="🎁 QUÀ TẶNG VOUCHER MỚI", color=discord.Color.green(), description="Cảm ơn bạn đã tin tưởng ủng hộ shop!")
                embed_b.add_field(name="🎫 Mã Voucher", value=f"`{code_b}`", inline=True)
                embed_b.add_field(name="📉 Giảm giá", value=f"**{percent_buyer}%**", inline=True)
                embed_b.add_field(name="⏰ Hạn dùng", value="7 Ngày (Dùng 1 lần)", inline=True)
                embed_b.set_footer(text="Sử dụng mã này cho đơn hàng tiếp theo để nhận ưu đãi!")
                if guild.icon: embed_b.set_thumbnail(url=guild.icon.url)
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
                    embed_i.description = f"Người bạn bạn mời {user.mention} vừa mua đơn hàng đầu tiên!"
                    embed_i.add_field(name="🎫 Voucher tặng bạn", value=f"`{code_i}`", inline=True)
                    embed_i.add_field(name="📉 Mức giảm", value="**20%**", inline=True)
                    embed_i.add_field(name="⏰ Hạn dùng", value="7 Ngày", inline=True)
                    embed_i.set_footer(text="Cảm ơn bạn đã giới thiệu thành viên mới! ❤️")
                    if guild.icon: embed_i.set_thumbnail(url=guild.icon.url)
                    await inviter.send(embed=embed_i)
                except: pass
        conn.close()

    # --- XỬ LÝ ÁP DỤNG VOUCHER TRONG TICKET ---
    async def process_voucher_logic(self, interaction, code, order_code):
        import sell_system # Import để lấy bank_waiting
        code = code.upper()
        user_id = interaction.user.id
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        conn = sqlite3.connect('bank_orders.db')
        c = conn.cursor()
        
        # Kiểm tra voucher người dùng
        c.execute("SELECT percent FROM vouchers WHERE user_id = ? AND code = ? AND used = 0 AND expiry_date > ?", (user_id, code, now))
        res = c.fetchone()
        
        is_admin_vouch = False
        if not res:
            # Kiểm tra voucher admin (chung)
            c.execute("SELECT percent, max_uses, current_uses FROM admin_vouchers WHERE code = ? AND expiry_date > ?", (code, now))
            res = c.fetchone()
            if res and res[2] < res[1]:
                is_admin_vouch = True
            else:
                res = None

        if res:
            percent = res[0]
            if order_code in sell_system.bank_waiting:
                old_price = sell_system.bank_waiting[order_code]['price']
                discount = int(old_price * (percent / 100))
                new_price = max(0, old_price - discount)
                
                # Cập nhật giá mới
                sell_system.bank_waiting[order_code]['price'] = new_price
                sell_system.db_save_waiting(order_code, interaction.channel.id, 
                                          sell_system.bank_waiting[order_code]['product'], 
                                          sell_system.bank_waiting[order_code]['link'], 
                                          new_price, user_id)
                
                # Đánh dấu đã dùng
                if is_admin_vouch:
                    conn.execute("UPDATE admin_vouchers SET current_uses = current_uses + 1 WHERE code = ?", (code,))
                else:
                    conn.execute("UPDATE vouchers SET used = 1 WHERE user_id = ? AND code = ?", (user_id, code))
                
                conn.commit()
                conn.close()

                embed = discord.Embed(title="✅ ÁP DỤNG THÀNH CÔNG", color=discord.Color.green())
                embed.description = f"Mã `{code}` đã giảm **{percent}%** cho đơn hàng của bạn."
                embed.add_field(name="💰 Giá cũ", value=f"{old_price:,} VND", inline=True)
                embed.add_field(name="💵 Giá mới", value=f"**{new_price:,} VND**", inline=True)
                embed.set_footer(text="Vui lòng nhấn 'Chuyển Khoản' lại để cập nhật mã QR mới!")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return True
        
        conn.close()
        return False

    # --- CÁC HÀM HỖ TRỢ ---
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

    @commands.command(name="vouchers")
    async def list_vouchers(self, ctx):
        conn = sqlite3.connect('bank_orders.db')
        c = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        c.execute("SELECT code, percent, expiry_date FROM vouchers WHERE user_id = ? AND used = 0 AND expiry_date > ?", (ctx.author.id, now))
        rows = c.fetchall()
        conn.close()
        
        embed = discord.Embed(title="🎫 KHO VOUCHER CỦA BẠN", color=discord.Color.blue())
        if rows:
            for r in rows:
                embed.add_field(name=f"Mã: {r[0]}", value=f"Giảm: **{r[1]}%**\nHạn dùng: {r[2]}", inline=False)
        else:
            embed.description = "Bạn hiện không có mã giảm giá nào còn hạn."
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(InviteSystem(bot))
