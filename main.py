import os
import time
import threading
import logging
import requests
import pandas as pd
import ta
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


# ============================================================
# CONFIG
# ============================================================

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN pa jwenn nan Environment Variables.")

bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")

BYBIT_URL = "https://api.bybit.com/v5/market/kline"

TIMEFRAME = "1"
CANDLE_LIMIT = 200

SYMBOLS = {
    "BTCUSDT": "BTC/USDT",
    "ETHUSDT": "ETH/USDT",
    "SOLUSDT": "SOL/USDT",
    "XRPUSDT": "XRP/USDT",
}

user_sessions = {}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


# ============================================================
# SESSION
# ============================================================

def get_session(chat_id):
    if chat_id not in user_sessions:
        user_sessions[chat_id] = {
            "pair": "BTCUSDT",
            "timeframe": "1"
        }

    return user_sessions[chat_id]


# ============================================================
# GET MARKET DATA FROM BYBIT
# ============================================================

def get_market_data(symbol):

    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": TIMEFRAME,
        "limit": CANDLE_LIMIT
    }

    response = requests.get(
        BYBIT_URL,
        params=params,
        timeout=10
    )

    response.raise_for_status()

    data = response.json()

    if data.get("retCode") != 0:
        raise RuntimeError(
            f"Bybit API error: {data.get('retMsg', 'Unknown error')}"
        )

    candles = data.get("result", {}).get("list", [])

    if len(candles) < 100:
        raise RuntimeError("Pa gen ase candles pou analiz la.")

    columns = [
        "time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "turnover"
    ]

    df = pd.DataFrame(candles, columns=columns)

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "turnover"
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    df["time"] = pd.to_numeric(
        df["time"],
        errors="coerce"
    )

    df = df.dropna()

    # Bybit bay newest candle an premye.
    df = df.sort_values("time").reset_index(drop=True)

    # Nou pa itilize candle ki poko fini an.
    if len(df) > 1:
        df = df.iloc[:-1].copy()

    if len(df) < 100:
        raise RuntimeError("Pa gen ase candles fèmen.")

    return df


# ============================================================
# INDICATORS
# ============================================================

def calculate_indicators(df):

    df["EMA20"] = ta.trend.ema_indicator(
        df["close"],
        window=20
    )

    df["EMA50"] = ta.trend.ema_indicator(
        df["close"],
        window=50
    )

    df["CCI"] = ta.trend.cci(
        df["high"],
        df["low"],
        df["close"],
        window=14
    )

    df["STOCH_K"] = ta.momentum.stoch(
        df["high"],
        df["low"],
        df["close"],
        window=14
    )

    df["STOCH_D"] = ta.momentum.stoch_signal(
        df["high"],
        df["low"],
        df["close"],
        window=14
    )

    df["RSI"] = ta.momentum.rsi(
        df["close"],
        window=14
    )

    macd = ta.trend.MACD(
        df["close"],
        window_slow=26,
        window_fast=12,
        window_sign=9
    )

    df["MACD"] = macd.macd()
    df["MACD_SIGNAL"] = macd.macd_signal()
    df["MACD_DIFF"] = macd.macd_diff()

    return df


# ============================================================
# MARKET ANALYSIS
# ============================================================

def analiz_mache_reyel(symbol):

    try:

        # 1. Get real candles
        df = get_market_data(symbol)

        # 2. Calculate indicators
        df = calculate_indicators(df)

        last = df.iloc[-1]

        required = [
            "EMA20",
            "EMA50",
            "CCI",
            "STOCH_K",
            "STOCH_D",
            "RSI",
            "MACD_DIFF"
        ]

        if any(pd.isna(last[x]) for x in required):
            return "NO_TRADE", 0, [
                "Indicator yo poko pare."
            ]

        close = float(last["close"])
        ema20 = float(last["EMA20"])
        ema50 = float(last["EMA50"])
        cci = float(last["CCI"])
        stoch_k = float(last["STOCH_K"])
        stoch_d = float(last["STOCH_D"])
        rsi = float(last["RSI"])
        macd_diff = float(last["MACD_DIFF"])

        buy_score = 0
        sell_score = 0

        buy_reasons = []
        sell_reasons = []

        # ----------------------------------------------------
        # EMA TREND = 30 points
        # ----------------------------------------------------

        if ema20 > ema50:
            buy_score += 30
            buy_reasons.append("EMA20 > EMA50")

        elif ema20 < ema50:
            sell_score += 30
            sell_reasons.append("EMA20 < EMA50")

        # ----------------------------------------------------
        # PRICE vs EMA20 = 20 points
        # ----------------------------------------------------

        if close > ema20:
            buy_score += 20
            buy_reasons.append("Price > EMA20")

        elif close < ema20:
            sell_score += 20
            sell_reasons.append("Price < EMA20")

        # ----------------------------------------------------
        # CCI = 20 points
        # ----------------------------------------------------

        if cci > 0:
            buy_score += 20
            buy_reasons.append("CCI bullish")

        elif cci < 0:
            sell_score += 20
            sell_reasons.append("CCI bearish")

        # ----------------------------------------------------
        # STOCHASTIC = 15 points
        # ----------------------------------------------------

        if stoch_k > stoch_d:
            buy_score += 15
            buy_reasons.append("Stochastic bullish")

        elif stoch_k < stoch_d:
            sell_score += 15
            sell_reasons.append("Stochastic bearish")

        # ----------------------------------------------------
        # RSI = 15 points
        # ----------------------------------------------------

        if 50 < rsi < 70:
            buy_score += 15
            buy_reasons.append("RSI bullish zone")

        elif 30 < rsi < 50:
            sell_score += 15
            sell_reasons.append("RSI bearish zone")

        # ----------------------------------------------------
        # MACD = 10 points
        # ----------------------------------------------------

        if macd_diff > 0:
            buy_score += 10
            buy_reasons.append("MACD bullish")

        elif macd_diff < 0:
            sell_score += 10
            sell_reasons.append("MACD bearish")

        # ----------------------------------------------------
        # DECISION
        # ----------------------------------------------------

        best_score = max(
            buy_score,
            sell_score
        )

        score_difference = abs(
            buy_score - sell_score
        )

        # Pa ase fòse yon signal.
        if best_score < 80:
            return "NO_TRADE", best_score, [
                "Konfimasyon teknik pa ase."
            ]

        # Si BUY ak SELL twò pre, pa pran signal.
        if score_difference < 10:
            return "NO_TRADE", best_score, [
                "BUY ak SELL twò pre."
            ]

        if buy_score > sell_score:
            return "BUY 🟢", buy_score, buy_reasons

        return "SELL 🔴", sell_score, sell_reasons

    except Exception as e:

        logging.error(
            "Market analysis error: %s",
            e
        )

        # Pa janm envante BUY/SELL lè API a gen pwoblèm.
        return "NO_TRADE", 0, [
            "Market data pa disponib kounye a."
        ]


# ============================================================
# MAIN MENU
# ============================================================

@bot.message_handler(commands=["start"])
def main_menu(message):

    chat_id = message.chat.id

    get_session(chat_id)

    markup = InlineKeyboardMarkup()

    markup.add(
        InlineKeyboardButton(
            "🚀 Scan Live Market",
            callback_data="menu_signals"
        )
    )

    bot.send_message(
        chat_id,
        "🤖 *SMESH TRADING | TECHNICAL SIGNAL ENGINE*\n\n"
        "📡 *Status:* Live market data\n"
        "📊 *Indicators:* EMA • CCI • Stochastic • RSI • MACD\n"
        "⏱ *Timeframe:* 1 Minute\n\n"
        "⚠️ Signal la se yon analiz teknik, "
        "li pa yon garanti rezilta.\n\n"
        "Chwazi asset ou vle analize:",
        reply_markup=markup
    )


# ============================================================
# CALLBACKS
# ============================================================

@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):

    chat_id = call.message.chat.id

    session = get_session(chat_id)

    bot.answer_callback_query(call.id)

    # --------------------------------------------------------
    # SHOW PAIRS
    # --------------------------------------------------------

    if call.data == "menu_signals":

        markup = InlineKeyboardMarkup()

        markup.row(
            InlineKeyboardButton(
                "BTC/USDT",
                callback_data="pair_BTCUSDT"
            ),
            InlineKeyboardButton(
                "ETH/USDT",
                callback_data="pair_ETHUSDT"
            )
        )

        markup.row(
            InlineKeyboardButton(
                "SOL/USDT",
                callback_data="pair_SOLUSDT"
            ),
            InlineKeyboardButton(
                "XRP/USDT",
                callback_data="pair_XRPUSDT"
            )
        )

        bot.send_message(
            chat_id,
            "💎 *SELECT AN ASSET:*",
            reply_markup=markup
        )

    # --------------------------------------------------------
    # SELECT PAIR
    # --------------------------------------------------------

    elif call.data.startswith("pair_"):

        symbol = call.data.replace(
            "pair_",
            ""
        )

        if symbol not in SYMBOLS:
            bot.send_message(
                chat_id,
                "❌ Asset sa pa disponib."
            )
            return

        session["pair"] = symbol

        # Nou pase symbol dirèkteman pou thread la
        # pa pran yon lòt pair si user la klike rapid.
        threading.Thread(
            target=animasyon_siyal,
            args=(chat_id, symbol),
            daemon=True
        ).start()


# ============================================================
# SIGNAL SCAN
# ============================================================

def animasyon_siyal(chat_id, symbol):

    pair_name = SYMBOLS.get(
        symbol,
        symbol
    )

    msg_wait = bot.send_message(
        chat_id,
        f"🔍 *Scanning {pair_name}...*\n\n"
        "📊 EMA\n"
        "📊 CCI\n"
        "📊 Stochastic\n"
        "📊 RSI\n"
        "📊 MACD\n\n"
        "⏳ Please wait..."
    )

    try:

        time.sleep(2)

        signal, score, reasons = analiz_mache_reyel(
            symbol
        )

        try:
            bot.delete_message(
                chat_id,
                msg_wait.message_id
            )
        except Exception:
            pass

        markup = InlineKeyboardMarkup()

        markup.add(
            InlineKeyboardButton(
                "🔄 Scan Again",
                callback_data="menu_signals"
            )
        )

        if signal == "NO_TRADE":

            bot.send_message(
                chat_id,
                f"⏸ *NO TRADE*\n\n"
                f"📊 Asset: *{pair_name}*\n"
                f"⏱ Timeframe: *1 Minute*\n"
                f"📈 Technical Score: *{score}/110*\n\n"
                f"⚠️ Konfimasyon pa ase pou bay "
                f"yon BUY/SELL.\n\n"
                f"🧠 Reason:\n"
                f"• {reasons[0]}",
                reply_markup=markup
            )

            return

        logo = (
            "🟩 BUY 🟩"
            if "BUY" in signal
            else
            "🟥 SELL 🟥"
        )

        reason_text = "\n".join(
            f"• {reason}"
            for reason in reasons
        )

        bot.send_message(
            chat_id,
            f"🎯 *TECHNICAL SIGNAL*\n\n"
            f"📊 Asset: *{pair_name}*\n"
            f"⏱ Timeframe: *1 Minute*\n"
            f"📈 Technical Score: *{score}/110*\n\n"
            f"🚀 *Action: {logo}*\n\n"
            f"🧠 *Confirmations:*\n"
            f"{reason_text}\n\n"
            f"⚠️ Score sa a se yon score teknik, "
            f"li pa yon pousantaj garanti.",
            reply_markup=markup
        )

    except Exception as e:

        logging.error(
            "Signal display error: %s",
            e
        )

        bot.send_message(
            chat_id,
            "❌ Gen yon pwoblèm pandan scan an.\n"
            "Eseye ankò pita."
        )


# ============================================================
# STATUS COMMAND
# ============================================================

@bot.message_handler(commands=["status"])
def status_command(message):

    try:

        df = get_market_data("BTCUSDT")

        bot.send_message(
            message.chat.id,
            f"🟢 *SYSTEM ONLINE*\n\n"
            f"📡 Bybit API: OK\n"
            f"📊 BTCUSDT candles: {len(df)}\n"
            f"⏱ Timeframe: 1 Minute"
        )

    except Exception as e:

        logging.error(
            "Status error: %s",
            e
        )

        bot.send_message(
            message.chat.id,
            "🔴 *MARKET DATA OFFLINE*\n\n"
            "Bybit data pa disponib kounye a."
        )


# ============================================================
# START BOT
# ============================================================

print("⚡ Technical Signal Bot starting...")

bot.infinity_polling(
    timeout=20,
    long_polling_timeout=20
    )
