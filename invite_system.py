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
# ID Kênh quản lý Voucher Admin (Nơi nhận báo cáo log)
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
        print("✅ Hệ thống Invite & Voucher đã sẵn sàng.")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        inviter = await self.get_inviter(member)
        if inviter and not inviter.bot:
            conn = sqlite3.connect('bank_orders.db')
            conn.execute("INSERT OR IGNORE INTO affiliate_rewards (inviter_id, invited_id, rewarded) VALUES (?, ?, 0)", 
                         (inviter.id, member.id))
            conn.commit()
            conn.close()

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
        """Thông báo khi khách SỬ DỤNG voucher"""
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

    async def log_voucher_gift(self, receiver, code, percent, reason):
        """Thông báo cho Admin khi hệ thống TẶNG voucher cho khách"""
        channel = self.bot.get_channel(ADMIN_VOUCHER_LOG_ID)
        if not channel: return

        embed = discord.Embed(title="🎁 HỆ THỐNG TẶNG VOUCHER", color=0x2ecc71)
        embed.add_field(name="👤 Người nhận", value=f"{receiver.mention} ({receiver.id})", inline=False)
        embed.add_field(name="🎫 Mã được tạo", value=f"`{code}`", inline=True)
        embed.add_field(name="📉 Mức giảm", value=f"{percent}%", inline=True)
        embed.add_field(name="📝 Lý do", value=reason, inline=False)
        embed.set_footer(text="Voucher này đã được lưu vào Database cá nhân.")
        embed.timestamp = discord.utils.utcnow()

        try: await channel.send(embed=embed)
        except: pass

    # --- LỆNH XÓA VOUCHER CHO ADMIN VỚI LÝ DO ---
    @commands.command(name="delvoucher")
    @commands.has_permissions(administrator=True)
    async def delvoucher(self, ctx, code: str, *, reason: str = "Không có lý do cụ thể"):
        """Xóa mã voucher và thông báo lý do cho khách"""
        code = code.upper()
        conn = sqlite3.connect('bank_orders.db')
        c = conn.cursor()
        
        # Kiểm tra xem voucher có thuộc về ai không trước khi xóa
        c.execute("SELECT user_id, percent FROM vouchers WHERE code = ?", (code,))
        personal_data = c.fetchone()
        
        # Xóa ở bảng admin
        c.execute("DELETE FROM admin_vouchers WHERE code = ?", (code,))
        admin_deleted = c.rowcount
        
        # Xóa ở bảng cá nhân
        c.execute("DELETE FROM vouchers WHERE code = ?", (code,))
        personal_deleted = c.rowcount
        
        conn.commit()
        conn.close()
        
        if admin_deleted > 0 or personal_deleted > 0:
            await ctx.send(f"✅ Đã xóa mã Voucher: `{code}`. Lý do: **{reason}**")
            
            # Gửi DM cho khách nếu là voucher cá nhân
            if personal_data:
                user_id, percent = personal_data
                try:
                    target_user = await self.bot.fetch_user(user_id)
                    if target_user:
                        dm_embed = discord.Embed(
                            title="📢 THÔNG BÁO THU HỒI VOUCHER",
                            description=f"Chào **{target_user.name}**, chúng mình rất tiếc phải thông báo về việc thay đổi mã giảm giá cá nhân của bạn.",
                            color=0xe74c3c # Màu đỏ cảnh báo nhưng lịch sự
                        )
                        dm_embed.add_field(name="🎫 Mã Voucher", value=f"`{code}`", inline=True)
                        dm_embed.add_field(name="📉 Mức giảm", value=f"{percent}%", inline=True)
                        dm_embed.add_field(name="📝 Lý do thu hồi", value=f"**{reason}**", inline=False)
                        dm_embed.add_field(
                            name="🧡 Lời nhắn từ Shop", 
                            value="Đừng buồn nhé! Bạn vẫn có thể nhận thêm các ưu đãi khác bằng cách tham gia các hoạt động hoặc tiếp tục ủng hộ Shop. Hẹn gặp lại bạn!", 
                            inline=False
                        )
                        dm_embed.set_footer(text="Đội ngũ hỗ trợ LoTuss's Shop")
                        dm_embed.timestamp = discord.utils.utcnow()
                        await target_user.send(embed=dm_embed)
                except:
                    pass # Khách khóa DM hoặc không tìm thấy user

            # Log việc xóa vào kênh admin
            log_ch = self.bot.get_channel(ADMIN_VOUCHER_LOG_ID)
            if log_ch:
                log_embed = discord.Embed(title="🗑️ LOG XÓA VOUCHER", color=0x34495e)
                log_embed.add_field(name="👤 Admin thực hiện", value=ctx.author.mention, inline=True)
                log_embed.add_field(name="🎫 Mã bị xóa", value=f"`{code}`", inline=True)
                log_embed.add_field(name="📝 Lý do", value=reason, inline=False)
                log_embed.timestamp = discord.utils.utcnow()
                await log_ch.send(embed=log_embed)
        else:
            await ctx.send(f"❌ Không tìm thấy mã Voucher `{code}` nào để xóa.")

    async def give_voucher_logic(self, member, product_name, amount, guild):
        """Xử lý tặng Voucher bí mật và thông báo Admin"""
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

        if old_order_count == 0:
            expiry_str = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
            c.execute("SELECT inviter_id FROM affiliate_rewards WHERE invited_id = ? AND rewarded = 0", (user_id,))
            aff_res = c.fetchone()

            v_code_buyer = self.generate_voucher()
            conn.execute("INSERT INTO vouchers (user_id, code, percent, used, expiry_date) VALUES (?, ?, 20, 0, ?)", (user_id, v_code_buyer, expiry_str))
            conn.commit()
            
            await self.log_voucher_gift(member, v_code_buyer, 20, "Mua hàng lần đầu tại shop")

            try:
                embed = discord.Embed(title="🎁 QUÀ TẶNG LẦN ĐẦU MUA HÀNG", color=0x2ecc71)
                embed.description = f"Cảm ơn bạn đã tin dùng dịch vụ của ***LoTuss's Shop***!\nVì đây là đơn hàng đầu tiên, shop tặng bạn 1 mã giảm giá 20% cho lần sau."
                embed.add_field(name="🎫 Mã Voucher", value=f"`{v_code_buyer}`", inline=True)
                embed.add_field(name="⏰ Hạn dùng", value="7 Ngày", inline=True)
                await member.send(embed=embed)
            except: pass

            if aff_res:
                inviter_id = aff_res[0]
                c.execute("SELECT COUNT(*) FROM affiliate_rewards WHERE inviter_id = ? AND rewarded = 1", (inviter_id,))
                vouchers_sent = c.fetchone()[0]

                if vouchers_sent < 3:
                    v_code_inviter = self.generate_voucher()
                    conn.execute("INSERT INTO vouchers (user_id, code, percent, used, expiry_date) VALUES (?, ?, 20, 0, ?)", (inviter_id, v_code_inviter, expiry_str))
                    conn.execute("UPDATE affiliate_rewards SET rewarded = 1 WHERE invited_id = ?", (user_id,))
                    conn.commit()
                    
                    inviter_user = await self.bot.fetch_user(inviter_id)
                    await self.log_voucher_gift(inviter_user, v_code_inviter, 20, f"Mời thành viên {member.name} mua đơn đầu")

                    try:
                        embed_inv = discord.Embed(title="🎊 THƯỞNG MỜI BẠN BÈ", color=0x3498db)
                        embed_inv.description = f"Thành viên **{member.name}** bạn mời đã mua đơn đầu thành công!\nShop tặng bạn mã giảm giá 20%."
                        embed_inv.add_field(name="🎫 Mã Voucher", value=f"`{v_code_inviter}`", inline=True)
                        await inviter_user.send(embed=embed_inv)
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
        
        embed = discord.Embed(
            title="✨ 🏆 BẢNG VÀNG ĐẠI GIA THANH TOÁN BẰNG BANK - LOTUSS'S SHOP 🏆 ✨", 
            description="*Nơi vinh danh những khách hàng thân thiết và chịu chi nhất hệ thống.*\n━━━━━━━━━━━━━━━━━━━━", 
            color=0xf1c40f
        )
        medals = ["🥇", "🥈", "🥉", "👤", "👤", "👤", "👤", "👤", "👤", "👤"]
        top_list = ""
        if not rows:
            top_list = "🚀 *Chưa có dữ liệu, hãy trở thành người đầu tiên!*"
        else:
            for i, r in enumerate(rows):
                user_tag = f"<@{r[0]}>"
                money = f"{r[1]:,}"
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
            
            log_ch = self.bot.get_channel(ADMIN_VOUCHER_LOG_ID)
            if log_ch:
                await log_ch.send(f"🆕 Admin **{ctx.author}** đã tạo mã Voucher chung `{code}` ({percent}%).")
        except sqlite3.IntegrityError:
            await ctx.send("❌ Mã Voucher này đã tồn tại!")
        finally:
            conn.close()

async def setup(bot):
    await bot.add_cog(InviteSystem(bot))
