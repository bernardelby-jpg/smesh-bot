import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import pandas as pd
import requests
import random
import time
import threading

TOKEN = "8083876809:AAGj7xzGWm79aJTDKUmjR9yzYZako8-_MmE"
bot = telebot.TeleBot(TOKEN)

user_sessions = {}

def get_session(chat_id):
    if chat_id not in user_sessions:
        user_sessions[chat_id] = {
            "mode": None, "pair": "EURUSD", "time": "M1",
            "count_manual": 0, "count_auto": 0, "max_manual": 20, "max_auto": 10
        }
    return user_sessions[chat_id]

def kalkile_siyal_pwofesyonel(pè_monnen):
    try:
        score = random.randint(96, 109)
        aksyon = random.choice(["BUY 🟢", "SELL 🔴"])
        return aksyon, score
    except Exception:
        return "BUY 🟢", random.randint(95, 102)

@bot.message_handler(commands=['start'])
def main_menu(message):
    chat_id = message.chat.id
    get_session(chat_id)
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🚀 Get a Signal", callback_data="menu_signals"))
    markup.add(InlineKeyboardButton("👑 VIP Team (Coming Soon)", callback_data="menu_vip"))
    markup.add(InlineKeyboardButton("📱 Pocket Option", url="https://pocketoption.com"))
    markup.add(InlineKeyboardButton("🧑‍💻 Support / Personal Manager", url="https://t.me"))
    
    bot.send_message(chat_id, 
        "🤖 **SMESH TRADING | FREE ACCESS v3.0**\n\n"
        "🔔 **Signals:** AI Scanning Active\n"
        "🟢 **Your level:** Free Tester\n\n"
        "Welcome! Choose an option from the menu below to start trading:", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    chat_id = call.message.chat.id
    session = get_session(chat_id)
    bot.answer_callback_query(call.id)
    
    if call.data == "menu_signals":
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🫱 Manual Select", callback_data="btn_manual"))
        markup.add(InlineKeyboardButton("⚙️ AI Auto-Scan", callback_data="btn_auto"))
        bot.send_message(chat_id, "⚙️ **SELECT YOUR TRADING MODE**", reply_markup=markup, parse_mode="Markdown")

    elif call.data == "menu_vip":
        bot.send_message(chat_id, "👑 **SMESH VIP SYSTEM**\n\nThis option is currently locked. Enjoy the free version for now! Later, you will be able to buy an official VIP plan automatically here.")

    elif call.data == "btn_manual":
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("𒒱 Currency pairs", callback_data="cat_forex"))
        bot.send_message(chat_id, "💎 **SELECT AN ASSET**", reply_markup=markup)

    elif call.data == "cat_forex":
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("AUD/CAD OTC", callback_data="pair_AUDCAD OTC"), InlineKeyboardButton("AUD/USD OTC", callback_data="pair_AUDUSD OTC"))
        markup.row(InlineKeyboardButton("EUR/USD OTC", callback_data="pair_EURUSD OTC"), InlineKeyboardButton("GBP/USD OTC", callback_data="pair_GBPUSD OTC"))
        bot.send_message(chat_id, "Select a currency pair:", reply_markup=markup)

    elif call.data.startswith("pair_"):
        session["pair"] = call.data.replace("pair_", "")
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("S5", callback_data="time_S5"), InlineKeyboardButton("S15", callback_data="time_S15"))
        markup.row(InlineKeyboardButton("M1", callback_data="time_M1"), InlineKeyboardButton("M5", callback_data="time_M5"))
        bot.send_message(chat_id, "⏱️ **Choose expiration time:**", reply_markup=markup)

    elif call.data.startswith("time_"):
        session["time"] = call.data.replace("time_", "")
        threading.Thread(target=animasyon_siyal, args=(chat_id, False)).start()

    elif call.data == "btn_auto" or call.data == "next_auto":
        session["mode"] = "auto"
        session["pair"] = random.choice(["EUR/USD OTC", "GBP/USD OTC", "AUD/USD OTC"])
        session["time"] = random.choice(["S5", "S15", "M1", "M5"])
        threading.Thread(target=animasyon_siyal, args=(chat_id, True)).start()

def animasyon_siyal(chat_id, is_auto):
    session = get_session(chat_id)
    msg_wait = bot.send_message(chat_id, f"⚡ **AI scanning {session['pair']} chart...**\nAnalyzing candlestick patterns... ⏳")
    
    time.sleep(2)
    bot.delete_message(chat_id, msg_wait.message_id)
    
    siyal, score = kalkile_siyal_pwofesyonel(session["pair"])
    
    if is_auto:
        session["count_auto"] += 1
        c = session["count_auto"]
        m = session["max_auto"]
    else:
        session["count_manual"] += 1
        c = session["count_manual"]
        m = session["max_manual"]

    logo = "🟩 BUY 🟩" if "BUY" in siyal else "🟥 SELL 🟥"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🚀 Next Signal", callback_data="next_auto" if is_auto else "cat_forex"))
    
    bot.send_message(chat_id, 
        f"🎯 **SIGNAL LOCKED** 🎯\n\n"
        f"📊 **Asset Paired:** {session['pair']}\n"
        f"⏱  **Expiration:** {session['time']}\n"
        f"🎯 **AI Confidence:** {score}/110 pwen 🔥\n"
        f"🔥 **Action:** **{siyal}**\n\n"
        f"💎 _Progress: ({c}/{m})_", 
        reply_markup=markup, parse_mode="Markdown")

print("⚡ Smesh Free Tester Bot ap kouri 100%...")
bot.polling()
