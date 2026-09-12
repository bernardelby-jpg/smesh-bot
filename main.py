import os
import time
import threading
import telebot
import pandas as pd
import ta
import yfinance as yf
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Secure Token Loading from Render Environment Variables
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing.")

bot = telebot.TeleBot(TOKEN)
user_sessions = {}
backtest_lock = threading.Lock()
running_backtests = set()

def get_session(chat_id):
    if chat_id not in user_sessions:
        user_sessions[chat_id] = {"pair": "EURUSD=X"}
    return user_sessions[chat_id]

# ============================================================
# LIVE FOREX REAL-TIME SIGNAL ENGINE (ULTRA-FAST)
# ============================================================

def calculate_live_signal(ticker_symbol):
    """
    ULTRA-FAST SIGNAL ENGINE v3.3
    Downloads only 1 day of 5-minute data to compute the signal in under 2 seconds.
    Bypasses long backtest loops to output instant results.
    """
    try:
        # Download only 1 day of history for maximum speed
        df = yf.download(tickers=ticker_symbol, period="1d", interval="5m", progress=False, auto_adjust=False)
        
        if df.empty or len(df) < 50:
            return "⏳ NO SIGNAL"
            
        # Flatten MultiIndex column format from yfinance feed
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df = df.reset_index()
        df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close"}, inplace=True)
        
        # Calculate technical indicators on the live feed
        df['EMA20'] = ta.trend.ema_indicator(df['close'], window=20)
        df['EMA50'] = ta.trend.ema_indicator(df['close'], window=50)
        df['RSI'] = ta.momentum.rsi(df['close'], window=14)
        df['CCI'] = ta.trend.cci(df['high'], df['low'], df['close'], window=14)
        
        macd = ta.trend.MACD(df['close'])
        df['MACD_DIFF'] = macd.macd_diff()
        df = df.dropna().reset_index(drop=True)
        
        if df.empty:
            return "⏳ NO SIGNAL"
            
        # Isolate the very last completed 5-minute candle
        candle = df.iloc[-1]
        
        buy_score = 0
        sell_score = 0

        # Technical matrix rules
        if candle["EMA20"] > candle["EMA50"]: buy_score += 30
        if candle["RSI"] > 52: buy_score += 25
        if candle["CCI"] > 50: buy_score += 25
        if candle["MACD_DIFF"] > 0: buy_score += 30

        if candle["EMA20"] < candle["EMA50"]: sell_score += 30
        if candle["RSI"] < 48: sell_score += 25
        if candle["CCI"] < -50: sell_score += 25
        if candle["MACD_DIFF"] < 0: sell_score += 30

        final_score = max(buy_score, sell_score)
        score_gap = abs(buy_score - sell_score)

        # Strict threshold confirmation filtering
        if final_score < 85 or score_gap < 12:
            return "⏳ NO SIGNAL"

        if buy_score > sell_score:
            return "🟢 BUY"
        elif sell_score > buy_score:
            return "🔴 SELL"
            
        return "⏳ NO SIGNAL"
    except Exception as e:
        print(f"Live engine error: {e}")
        return "⏳ NO SIGNAL"

# ============================================================
# TELEGRAM CONTROL INTERFACE
# ============================================================

@bot.message_handler(commands=['start'])
def main_menu(message):
    chat_id = message.chat.id
    get_session(chat_id)
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🚀 Scan Live Market", callback_data="menu_backtest_v3_2"))
    markup.add(InlineKeyboardButton("🧑‍💻 System Support", url="https://t.me"))
    
    bot.send_message(chat_id, 
        "🤖 **SMESH FOREX | SIGNAL ENGINE v3.3**\n\n"
        "📡 **Status:** Live Forex Data Feed Active\n"
        "⏱ **Timeframe:** 5 Minutes (Ultra-Fast 2s Scan)\n"
        "🔍 **Matrix:** EMA • RSI • CCI • MACD\n\n"
        "Welcome! Select the button below to scan the active market structure:", 
        markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    chat_id = call.message.chat.id
    session = get_session(chat_id)
    bot.answer_callback_query(call.id)
    
    if call.data == "menu_backtest_v3_2":
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("EUR/USD", callback_data="pair_EURUSD=X"), InlineKeyboardButton("GBP/USD", callback_data="pair_GBPUSD=X"))
        markup.row(InlineKeyboardButton("AUD/USD", callback_data="pair_AUDUSD=X"), InlineKeyboardButton("USD/CAD", callback_data="pair_USDCAD=X"))
        bot.send_message(chat_id, "💎 **SELECT A FOREX ASSET FOR INSTANT SIYAL:**", reply_markup=markup)

    elif call.data.startswith("pair_"):
        ticker = call.data.replace("pair_", "", 1)
        session["pair"] = ticker

        with backtest_lock:
            if chat_id in running_backtests:
                bot.send_message(chat_id, "⏳ **Analyzing...** Please wait until the current scan finishes.")
                return
            running_backtests.add(chat_id)

        threading.Thread(target=process_live_signal, args=(chat_id,), daemon=True).start()

def process_live_signal(chat_id):
    try:
        session = get_session(chat_id)
        ticker = session["pair"]
        clean_name = ticker.replace("=X", "").replace("/", "")
        formatted_name = f"{clean_name[:3]}/{clean_name[3:]}" if len(clean_name) == 6 else clean_name
        
        wait_msg = bot.send_message(chat_id, f"🔍 **Analyzing {formatted_name}...** ⏳")
        
        # Execute the ultra-fast live matrix analysis
        signal_result = calculate_live_signal(ticker)
        
        try:
            bot.delete_message(chat_id, wait_msg.message_id)
        except Exception:
            pass
            
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔄 Scan Again", callback_data="menu_backtest_v3_2"))
        
        # Output layout matching the precise short text format requested
        bot.send_message(chat_id, 
            f"📊 **{formatted_name}**\n"
            f"{signal_result}\n"
            f"⏱ **5M**", 
            reply_markup=markup, parse_mode="Markdown")
            
    except Exception as e:
        print(f"Telegram processing error: {e}")
    finally:
        with backtest_lock:
            running_backtests.discard(chat_id)

if __name__ == "__main__":
    print("⚡ Ultra-Fast Forex Engine v3.3 running smoothly...")
    bot.infinity_polling(skip_pending=True)
