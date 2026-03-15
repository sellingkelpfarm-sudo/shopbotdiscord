import discord
from discord.ext import commands, tasks
import sqlite3
import random
import string
import asyncio
import os
from discord import utils
from datetime import datetime, timedelta

# ID Kênh thông báo chung (Nơi hiện thông báo mời thành viên)
NOTIFICATION_CHANNEL_ID = 1479205595604193432
# ID Kênh quản lý Voucher Admin
ADMIN_VOUCHER_LOG_ID = 1481611917905756341

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
    c.execute('''CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)''')
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
        print("✅ Hệ thống Invite đã sẵn sàng.")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Thông báo ngay khi có thành viên mới vào Group"""
        inviter = await self.get_inviter(member)
        if inviter and not inviter.bot:
            # Lưu vào Database để theo dõi phần thưởng sau này
            conn = sqlite3.connect('bank_orders.db')
            conn.execute("INSERT OR IGNORE INTO affiliate_rewards (inviter_id, invited_id, rewarded) VALUES (?, ?, 0)", 
                         (inviter.id, member.id))
            conn.commit()
            conn.close()

            # Thông báo công khai vào group
            notif_channel = self.bot.get_channel(NOTIFICATION_CHANNEL_ID)
            if notif_channel:
                await notif_channel.send(f"📥 **{inviter.mention}** đã mời **{member.mention}** vào server! Chào mừng bạn mới nhé! 🎉")

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

    def generate_voucher(self):
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

    async def send_voucher_webhook(self, user, code, percent, old_price, new_price, order_code, v_type):
        channel = self.bot.get_channel(ADMIN_VOUCHER_LOG_ID)
        if not channel: return
        
        embed = discord.Embed(title="🎫 BÁO CÁO SỬ DỤNG VOUCHER", color=discord.Color.blue())
        embed.add_field(name="👤 Người sử dụng", value=f"{user.mention} ({user.id})", inline=False)
        embed.add_field(name="🆔 Mã đơn hàng", value=f"`{order_code}`", inline=True)
        embed.add_field(name="🎫 Mã Voucher", value=f"`{code}`", inline=True)
        embed.add_field(name="📊 Loại", value=v_type, inline=True)
        embed.add_field(name="📉 Giảm giá", value=f"{percent}%", inline=True)
        embed.add_field(name="💰 Giá cũ", value=f"{old_price:,} VND", inline=True)
        embed.add_field(name="✅ Giá sau giảm", value=f"**{new_price:,} VND**", inline=True)
        
        embed.timestamp = discord.utils.utcnow()
        
        try: await channel.send(embed=embed)
        except: pass

    async def process_voucher_logic(self, interaction, code, order_code):
        import sell_system
        code = code.upper()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn = sqlite3.connect('bank_orders.db')
        c = conn.cursor()

        if order_code in sell_system.bank_waiting:
            if sell_system.bank_waiting[order_code].get('voucher_applied'):
                conn.close()
                return "ALREADY_USED", None

        c.execute("SELECT percent, max_uses, current_uses FROM admin_vouchers WHERE code = ? AND expiry_date > ?", (code, now))
        res = c.fetchone()
        
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
                    sell_system.bank_waiting[order_code]['voucher_applied'] = True
                    conn.execute("UPDATE vouchers SET used = 1 WHERE user_id = ? AND code = ?", (interaction.user.id, code))
                    conn.commit()
                    conn.close()
                    await self.send_voucher_webhook(interaction.user, code, percent, old_price, new_price, order_code, "Voucher Cá Nhân")
                    return percent, new_price
        
        if res and res[2] < res[1]:
            percent = res[0]
            if order_code in sell_system.bank_waiting:
                old_price = sell_system.bank_waiting[order_code]['price']
                new_price = int(old_price * (1 - percent/100))
                sell_system.bank_waiting[order_code]['price'] = new_price
                sell_system.bank_waiting[order_code]['voucher_applied'] = True
                conn.execute("UPDATE admin_vouchers SET current_uses = current_uses + 1 WHERE code = ?", (code,))
                conn.commit()
                conn.close()
                await self.send_voucher_webhook(interaction.user, code, percent, old_price, new_price, order_code, "Voucher Admin (Chung)")
                return percent, new_price
                
        conn.close()
        return None, None

    async def give_voucher_logic(self, member, product_name, amount, guild):
        """Xử lý tặng Voucher bí mật qua DMs sau khi thanh toán"""
        conn = sqlite3.connect('bank_orders.db')
        c = conn.cursor()
        user_id = member.id
        c.execute("SELECT order_count FROM leaderboard WHERE user_id = ?", (user_id,))
        res = c.fetchone()
        old_order_count = res[0] if res else 0
        
        conn.execute("INSERT INTO leaderboard (user_id, total_spent, order_count) VALUES (?, ?, 1) "
                     "ON CONFLICT(user_id) DO UPDATE SET total_spent = total_spent + ?, order_count = order_count + 1",
                     (user_id, amount, amount))
        conn.commit()

        # Nếu là đơn hàng đầu tiên
        if old_order_count == 0:
            expiry_str = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
            c.execute("SELECT inviter_id FROM affiliate_rewards WHERE invited_id = ? AND rewarded = 0", (user_id,))
            aff_res = c.fetchone()

            if aff_res:
                inviter_id = aff_res[0]
                c.execute("SELECT COUNT(*) FROM affiliate_rewards WHERE inviter_id = ? AND rewarded = 1", (inviter_id,))
                vouchers_sent = c.fetchone()[0]

                v_code_buyer = self.generate_voucher()
                conn.execute("INSERT INTO vouchers (user_id, code, percent, used, expiry_date) VALUES (?, ?, 20, 0, ?)", (user_id, v_code_buyer, expiry_str))
                conn.execute("UPDATE affiliate_rewards SET rewarded = 1 WHERE invited_id = ?", (user_id,))
                conn.commit()

                # DM riêng cho người mua
                try:
                    embed = discord.Embed(title="🎁 QUÀ TẶNG LẦN ĐẦU MUA HÀNG", color=0x2ecc71)
                    embed.description = f"Cảm ơn bạn đã tin dùng dịch vụ của ***LoTuss's Shop***!\nVì đây là đơn hàng đầu tiên, shop tặng bạn 1 mã giảm giá 20% cho lần sau."
                    embed.add_field(name="🎫 Mã Voucher", value=f"`{v_code_buyer}`", inline=True)
                    embed.add_field(name="📉 Giảm giá", value="**20%**", inline=True)
                    embed.add_field(name="⏰ Hạn dùng", value="7 Ngày", inline=True)
                    embed.set_footer(text="Nhấn 'NHẬP VOUCHER' trong đơn hàng tới để áp dụng nhé!")
                    await member.send(embed=embed)
                except: pass

                # Nếu người mời chưa nhận quá 3 voucher, tặng thêm cho người mời qua DM
                if vouchers_sent < 3:
                    v_code_inviter = self.generate_voucher()
                    conn.execute("INSERT INTO vouchers (user_id, code, percent, used, expiry_date) VALUES (?, ?, 20, 0, ?)", (inviter_id, v_code_inviter, expiry_str))
                    conn.commit()
                    
                    inviter = guild.get_member(inviter_id) or await self.bot.fetch_user(inviter_id)
                    try:
                        embed_inv = discord.Embed(title="🎊 THƯỞNG MỜI BẠN BÈ", color=0x3498db)
                        embed_inv.description = f"Thành viên **{member.name}** bạn mời đã mua đơn đầu thành công!\nShop tặng bạn mã giảm giá 20% (Lượt {vouchers_sent + 1}/3)."
                        embed_inv.add_field(name="🎫 Mã Voucher", value=f"`{v_code_inviter}`", inline=True)
                        embed_inv.add_field(name="⏰ Hạn dùng", value="7 Ngày", inline=True)
                        await inviter.send(embed=embed_inv)
                    except: pass
            else:
                # Không có người mời, chỉ tặng cho người mua qua DM
                voucher_code = self.generate_voucher()
                expiry_str = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
                conn.execute("INSERT INTO vouchers (user_id, code, percent, used, expiry_date) VALUES (?, ?, 20, 0, ?)", (user_id, voucher_code, expiry_str))
                conn.commit()
                try:
                    embed = discord.Embed(title="🎁 QUÀ TẶNG LẦN ĐẦU MUA HÀNG", color=0x2ecc71)
                    embed.description = f"Cảm ơn bạn đã tin dùng dịch vụ của ***LoTuss's Shop***!\nVì đây là đơn hàng đầu tiên, shop tặng bạn 1 mã giảm giá 20% cho lần sau."
                    embed.add_field(name="🎫 Mã Voucher", value=f"`{voucher_code}`", inline=True)
                    embed.add_field(name="📉 Giảm giá", value="**20%**", inline=True)
                    embed.add_field(name="⏰ Hạn dùng", value="7 Ngày", inline=True)
                    await member.send(embed=embed)
                except: pass
        conn.close()

    @tasks.loop(hours=1)
    async def update_top_task(self):
        await self.bot.wait_until_ready()
        conn = sqlite3.connect('bank_orders.db')
        c = conn.cursor()
        c.execute("SELECT value FROM config WHERE key = 'top_channel'")
        ch_res = c.fetchone()
        c.execute("SELECT value FROM config WHERE key = 'top_message'")
        msg_res = c.fetchone()
        if not ch_res:
            conn.close()
            return
        channel = self.bot.get_channel(int(ch_res[0]))
        if not channel:
            conn.close()
            return
        c.execute("SELECT user_id, total_spent FROM leaderboard ORDER BY total_spent DESC LIMIT 10")
        rows = c.fetchall()
        embed = discord.Embed(title="✨ 🏆 BẢNG VÀNG ĐẠI GIA THANH TOÁN BẰNG BANK - LOTUSS'S SHOP 🏆 ✨", description="*Nơi vinh danh những khách hàng thân thiết và chịu chi nhất hệ thống.*\n━━━━━━━━━━━━━━━━━━━━", color=0xf1c40f)
        medals = ["🥇", "🥈", "🥉", "👤", "👤", "👤", "👤", "👤", "👤", "👤"]
        top_list = ""
        if not rows:
            top_list = "🚀 *Chưa có dữ liệu, hãy trở thành người đầu tiên!*"
        else:
            for i, r in enumerate(rows):
                user_tag = f"<@{r[0]}>"; money = f"{r[1]:,}"
                if i < 3:
                    top_list += f"{medals[i]} **Top {i+1}: {user_tag}**\n┗ 💰 Tổng chi: `{money} VND`\n\n"
                else:
                    top_list += f"{medals[i]} Top {i+1}: {user_tag} | `{money} VND`\n"
        embed.add_field(name="💎 DANH SÁCH VINH DANH 💎", value=top_list, inline=False)
        embed.set_footer(text=f"🕒 Cập nhật tự động lúc: {datetime.now().strftime('%H:%M - %d/%m/%Y')}")
        message = None
        if msg_res:
            try: message = await channel.fetch_message(int(msg_res[0]))
            except: message = None
        if message: await message.edit(embed=embed)
        else:
            new_msg = await channel.send(embed=embed)
            conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('top_message', ?)", (str(new_msg.id),))
            conn.commit()
        conn.close()

    @commands.command(name="settop")
    @commands.has_permissions(administrator=True)
    async def settop(self, ctx):
        conn = sqlite3.connect('bank_orders.db')
        conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('top_channel', ?)", (str(ctx.channel.id),))
        conn.execute("DELETE FROM config WHERE key = 'top_message'")
        conn.commit()
        conn.close()
        await ctx.send("✅ Đã thiết lập kênh BXH duy nhất. Bot đang tạo bảng vinh danh...", delete_after=5)
        await self.update_top_task()

    @commands.command(name="createvoucher")
    @commands.has_permissions(administrator=True)
    async def createvoucher(self, ctx, code: str, percent: int, max_uses: int, days: int):
        code = code.upper()
        expiry_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        conn = sqlite3.connect('bank_orders.db')
        try:
            conn.execute("INSERT INTO admin_vouchers (code, percent, max_uses, expiry_date) VALUES (?, ?, ?, ?)", (code, percent, max_uses, expiry_date))
            conn.commit()
            await ctx.send(f"✅ Đã tạo Voucher chung: `{code}` giảm **{percent}%**, lượt dùng: **{max_uses}**, hạn: **{days} ngày**.")
        except sqlite3.IntegrityError:
            await ctx.send("❌ Mã Voucher này đã tồn tại!")
        finally:
            conn.close()

async def setup(bot):
    await bot.add_cog(InviteSystem(bot))
