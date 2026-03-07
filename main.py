import discord
from discord.ext import commands
import os

import requests
from flask import Flask, request
import threading
import hashlib
import time

from MenuRole import setup_menu
from sell_system import setup_sell

# ==============================
# DISCORD BOT TOKEN
# ==============================

TOKEN = os.getenv("TOKEN")

# ==============================
# DOITHES1 API KEY
# ==============================

DOITHES1_API_KEY = "0c8672410bf6ba8caeb009508b026ed9"

# ==============================
# DISCORD BOT SETUP
# ==============================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==============================
# BOT READY
# ==============================

@bot.event
async def on_ready():
    print(f"Bot đã online: {bot.user}")

    # Load hệ thống
    setup_menu(bot)
    setup_sell(bot)

# ==============================
# DOITHES1 CALLBACK SERVER
# ==============================

app = Flask(__name__)

@app.route('/callback', methods=['GET'])
def callback():

    status = request.args.get("status")
    request_id = request.args.get("request_id")
    amount = request.args.get("amount")
    telco = request.args.get("telco")

    print("========== CARD CALLBACK ==========")
    print("Status:", status)
    print("Request ID:", request_id)
    print("Amount:", amount)
    print("Telco:", telco)
    print("===================================")

    return "OK"

# ==============================
# RUN WEB SERVER (Railway)
# ==============================

def run_web():
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web).start()

# ==============================
# RUN DISCORD BOT
# ==============================

bot.run(TOKEN)

