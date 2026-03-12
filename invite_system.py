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
                 (user_id INTEGER PRIMARY KEY, total_spent INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value INTEGER)''')
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

    # --- TASK TỰ ĐỘNG CẬP NHẬT TOP (1 TIẾNG/LẦN) ---
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

        # Lấy Top 50 người dùng
        c.execute("SELECT user_id, total_spent FROM leaderboard ORDER BY total_spent DESC LIMIT 50")
        rows = c.fetchall()
        
        embed = discord.Embed(
            title="🏆 BẢNG XẾP HẠNG 50 ĐẠI GIA THANH TOÁN", 
            color=0xffd700,
            description="Vinh danh những khách hàng thân thiết nhất của LoTuss's Shop! ❤️"
        )
        
        if rows:
            # Chia làm nhiều trang nếu cần, nhưng ở đây dùng 1 list dài
            # Vì Discord giới hạn 4096 ký tự trong description nên 50 người vẫn đủ
            leaderboard_text = ""
            for i, r in enumerate(rows):
                if i == 0: emoji = "🥇"
                elif i == 1: emoji = "🥈"
                elif i == 2: emoji = "🥉"
                else: emoji = f"`#{i+1:02}`" # Định dạng số thứ tự 04, 05...
                
                leaderboard_text += f"{emoji} <@{r[0]}> — `{r[1]:,} VND`\n"
                
                # Tránh vượt quá giới hạn ký tự của Embed (tách nếu quá dài)
                if (i + 1) % 25 == 0:
                    embed.add_field(name=f"Top {i-23}-{i+1}", value=leaderboard_text, inline=False)
                    leaderboard_text = ""
            
            if leaderboard_text:
                embed.add_field(name=f"Danh sách tiếp theo", value=leaderboard_text, inline=False)
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

    # --- LOGIC VOUCHER & AFFILIATE ---
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

    async def process_voucher_logic(self, interaction, code, order_code):
        user_id, code, now = interaction.user.id, code.upper(), datetime.now()
        conn = sqlite3.connect('bank_orders.db')
        c = conn.cursor()
        
        c.execute("SELECT percent, max_uses, current_uses, expiry_date FROM admin_vouchers WHERE code = ?", (code,))
        res = c.fetchone()
        percent, is_admin = None, False
        if res:
            p, m, cur, exp = res
            if now > datetime.strptime(exp, '%Y-%m-%d %H:%M:%S') or cur >= m:
                conn.close()
                return False
            percent, is_admin = p, True
        else:
            c.execute("SELECT rowid, percent, expiry_date FROM vouchers WHERE user_id = ? AND code = ? AND used = 0", (user_id, code))
            res = c.fetchone()
            if res:
                rid, p, exp = res
                if now > datetime.strptime(exp, '%Y-%m-%d %H:%M:%S'):
                    conn.close()
                    return False
                percent, is_admin, row_id = p, False, rid
            else:
                conn.close()
                return False

        sell_mod = sys.modules.get('sell_system')
        if sell_mod and order_code in sell_mod.bank_waiting:
            old_p = sell_mod.bank_waiting[order_code]['price']
            new_p = int(old_p * (1 - percent / 100))
            sell_mod.bank_waiting[order_code]['price'] = new_p
            if is_admin: c.execute("UPDATE admin_vouchers SET current_uses = current_uses + 1 WHERE code = ?", (code,))
            else: c.execute("UPDATE vouchers SET used = 1 WHERE rowid = ?", (row_id,))
            conn.commit()
            conn.close()

            async for message in interaction.channel.history(limit=25):
                if message.author == self.bot.user and message.embeds:
                    if "XÁC NHẬN THANH TOÁN" in (message.embeds[0].title or ""):
                        embed = message.embeds[0]
                        embed.description = embed.description.replace(f"{old_p:,} VND", f"~~{old_p:,}~~ -> **{new_p:,} VND**")
                        embed.description += f"\n\n✨ **ĐÃ ÁP DỤNG VOUCHER: {code} (-{percent}%)**"
                        embed.color = 0xf1c40f
                        await message.edit(embed=embed)
                        break
            
            await interaction.response.send_message(f"✅ Áp dụng mã thành công!", ephemeral=True)
            return True
        conn.close()
        return False

    async def give_voucher_logic(self, user, product_name, amount, guild):
        conn = sqlite3.connect('bank_orders.db')
        expiry_str = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
        if self.count_active_vouchers(user.id) < 3:
            p_buyer = 50 if amount >= 100000 else 10
            code_buyer = self.generate_voucher()
            conn.execute("INSERT INTO vouchers (user_id, code, percent, used, expiry_date) VALUES (?, ?, ?, 0, ?)", (user.id, code_buyer, p_buyer, expiry_str))
        
        conn.execute("INSERT INTO leaderboard (user_id, total_spent) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET total_spent = total_spent + ?", (user.id, amount, amount))
        conn.commit()

        inviter = await self.get_inviter(user)
        if inviter and inviter.id != user.id:
            if self.count_active_vouchers(inviter.id) < 3:
                code_inviter = self.generate_voucher()
                conn.execute("INSERT INTO vouchers (user_id, code, percent, used, expiry_date) VALUES (?, ?, ?, 0, ?)", (inviter.id, code_inviter, 20, expiry_str))
                conn.commit()
                try: await inviter.send(f"🎁 Bạn nhận được mã **{code_inviter}** (20%) vì <@{user.id}> vừa mua hàng!")
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

async def setup(bot):
    await bot.add_cog(InviteSystem(bot))
