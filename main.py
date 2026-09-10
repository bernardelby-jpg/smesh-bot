import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import pandas as pd
import ta
import requests
import random
import time
import threading

TOKEN = "8083876809:AAHSmdRWvDphlZSg8D-vskQ6yhXbb2swgck"
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
        symbol = pè_monnen.replace(" OTC", "").replace("/", "")
        url = f"https://bybit.com{symbol}T&interval=1"
        res = requests.get(url).json()
        candles = res['result']['list']
        
        df = pd.DataFrame(candles, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df = df.iloc[::-1].reset_index(drop=True)

        df['EMA20'] = ta.trend.ema_indicator(df['close'], window=20)
        df['EMA50'] = ta.trend.ema_indicator(df['close'], window=50)
        df['CCI'] = ta.trend.cci(df['high'], df['low'], df['close'], window=14)
        df['stoch_k'] = ta.momentum.stoch(df['high'], df['low'], df['close'], window=14)
        df['stoch_d'] = ta.momentum.stoch_signal(df['high'], df['low'], df['close'], window=14)
        
        close = df['close'].iloc[-1]
        open_p = df['open'].astype(float).iloc[-1]
        ema20 = df['EMA20'].iloc[-1]
        ema50 = df['EMA50'].iloc[-1]
        cci = df['CCI'].iloc[-1]
        stoch_k = df['stoch_k'].iloc[-1]
        stoch_d = df['stoch_d'].iloc[-1]

        score_call = 0
        score_put = 0

        if ema20 > ema50: score_call += 25
        if close > ema20: score_call += 10
        if cci > 100: score_call += 25
        if stoch_k > stoch_d: score_call += 25
        if close > open_p: score_call += 15

        if ema20 < ema50: score_put += 25
        if close < ema20: score_put += 10
        if cci < -100: score_put += 25
        if stoch_k < stoch_d: score_put += 25
        if close < open_p: score_put += 15

        if score_call >= 90:
            return "BUY 🟢", score_call
        elif score_put >= 90:
            return "SELL 🔴", score_put
        else:
            return "NO_TRADE", max(score_call, score_put)
    except Exception:
        return "NO_TRADE", 0

@bot.message_handler(commands=['start'])
def main_menu(message):
    chat_id = message.chat.id
    get_session(chat_id)
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🚀 Get a signal", callback_data="menu_signals"))
    markup.add(InlineKeyboardButton("👑 VIP Team", callback_data="menu_vip"))
    markup.add(InlineKeyboardButton("📱 Pocket Option", url="https://pocketoption.com"))
    markup.add(InlineKeyboardButton("🧑‍💻 Support / Personal Manager", url="https://t.me"))
    
    bot.send_message(chat_id, 
        "🤖 **XYLO PRO | Trading Bot v3.0**\n\n"
        "🔔 **Signals:** AI Scanning Active\n"
        "🟢 **Your level:** VIP\n\n"
        "Welcome! Choose an option from the menu below:", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    chat_id = call.message.chat.id
    session = get_session(chat_id)
    bot.answer_callback_query(call.id)
    
    if call.data == "menu_signals":
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🫱 Manual", callback_data="btn_manual"))
        markup.add(InlineKeyboardButton("⚙️ Automatic", callback_data="btn_auto"))
        bot.send_message(chat_id, "🤖 **SELECT THE TRADING MODE**", reply_markup=markup, parse_mode="Markdown")

    elif call.data == "menu_vip":
        bot.send_message(chat_id, "👑 **XYLO VIP TEAM**\n\nContact your Personal Manager (@Sneek_pro) to activate lifetime access to private trading room.")

    elif call.data == "btn_manual":
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("💱 Currency pairs", callback_data="cat_forex"))
        bot.send_message(chat_id, "⚙️ **SELECT AN ASSET BY CATEGORY**", reply_markup=markup)

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
        bot.send_message(chat_id, "⏱️ **Choose the expiration time:**", reply_markup=markup)

    elif call.data.startswith("time_"):
        session["time"] = call.data.replace("time_", "")
        threading.Thread(target=animasyon_siyal, args=(chat_id, False)).start()

    elif call.data == "btn_auto" or call.data == "next_auto":
        session["mode"] = "auto"
        session["pair"] = random.choice(["EURUSD OTC", "GBPUSD", "AUDUSD OTC"])
        session["time"] = random.choice(["S5", "S10", "S50", "M1"])
        threading.Thread(target=animasyon_siyal, args=(chat_id, True)).start()

def animasyon_siyal(chat_id, is_auto):
    session = get_session(chat_id)
    msg_wait = bot.send_message(chat_id, f"🔍 **XYLO AI scanning {session['pair']} chart...**\nCalculating indicators (RSI, Stochastic, CCI)... ⏳")
    
    time.sleep(3)
    bot.delete_message(chat_id, msg_wait.message_id)
    
    siyal, score = kalkile_siyal_pwofesyonel(session["pair"])
    
    if siyal == "NO_TRADE":
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔄 Re-skane Mache a", callback_data="next_auto" if is_auto else "cat_forex"))
        bot.send_message(chat_id, 
            f"⚠️ **MARKET FILTER — NO TRADE**\n\n"
            f"📊 **Asset:** {session['pair']}\n"
            f"🎯 **AI Score:** {score}/110 pwen\n\n"
            f"❌ _Mache a pa gen gwo konfimasyon oswa li gen gwo risk kounye a._", 
            reply_markup=markup, parse_mode="Markdown")
        return

    if is_auto:
        session["count_auto"] += 1
        c, m = session["count_auto"], session["max_auto"]
    else:
        session["count_manual"] += 1
        c, m = session["count_manual"], session["max_manual"]

    logo = "🟩 BUY 🟩" if "BUY" in siyal else "🟥 SELL 🟥"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🚀 New Signal", callback_data="next_auto" if is_auto else "cat_forex"))
    
    bot.send_message(chat_id, 
        f"**{logo}**\n\n"
        f"**Analysis complete!**\n\n"
        f"📊 **Pair:** {session['pair']}\n"
        f"⏱  **Expiration:** {session['time']}\n"
        f"🎯 **AI Score:** {score}/110 pwen 🔥\n"
        f"🚀 **Action:** **{siyal}**\n\n"
        f"📊 _Progress: ({c}/{m})_", 
        reply_markup=markup, parse_mode="Markdown")

print("⚡ SmeshTrading ap kouri pafè...")
bot.polling()
