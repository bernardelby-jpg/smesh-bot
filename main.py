import os
import time
import threading
import requests
import pandas as pd
import ta
import telebot

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


# ============================================================
# SMESH SIGNAL ENGINE v6
# PAPER / SIMULATION VERSION
# ============================================================

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing.")

bot = telebot.TeleBot(TOKEN)

user_sessions = {}


# ============================================================
# USER SESSION
# ============================================================

def get_session(chat_id):
    if chat_id not in user_sessions:
        user_sessions[chat_id] = {
            "pair": "BTCUSDT"
        }

    return user_sessions[chat_id]


# ============================================================
# MARKET DATA
# ============================================================

def get_market_data(symbol):

    symbol = symbol.replace("/", "").replace(" OTC", "").upper()

    # Public market-data endpoint for simulation/testing.
    url = "https://api.bybit.com/v5/market/kline"

    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": "1",
        "limit": 200
    }

    try:

        response = requests.get(
            url,
            params=params,
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        if data.get("retCode") != 0:
            return None

        candles = data.get("result", {}).get("list", [])

        if len(candles) < 100:
            return None

        df = pd.DataFrame(
            candles,
            columns=[
                "time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "turnover"
            ]
        )

        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume"
        ]

        for column in numeric_columns:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce"
            )

        # Bybit returns newest first.
        df = df.iloc[::-1].reset_index(drop=True)

        # Don't use the currently forming candle.
        df = df.iloc[:-1].copy()

        return df

    except Exception as error:

        print("Market data error:", error)

        return None


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

    df["RSI"] = ta.momentum.rsi(
        df["close"],
        window=14
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

    df["MACD"] = ta.trend.macd(
        df["close"]
    )

    df["MACD_SIGNAL"] = ta.trend.macd_signal(
        df["close"]
    )

    df["ATR"] = ta.volatility.average_true_range(
        df["high"],
        df["low"],
        df["close"],
        window=14
    )

    return df.dropna().reset_index(drop=True)


# ============================================================
# CANDLE ANALYSIS
# ============================================================

def candle_confirmation(df):

    current = df.iloc[-1]

    candle_body = abs(
        current["close"] - current["open"]
    )

    candle_range = (
        current["high"] - current["low"]
    )

    if candle_range == 0:
        return 0, 0

    body_ratio = candle_body / candle_range

    bullish = current["close"] > current["open"]
    bearish = current["close"] < current["open"]

    buy_points = 0
    sell_points = 0

    if bullish and body_ratio >= 0.55:
        buy_points = 10

    if bearish and body_ratio >= 0.55:
        sell_points = 10

    return buy_points, sell_points


# ============================================================
# SUPPORT / RESISTANCE
# ============================================================

def support_resistance(df):

    recent = df.tail(30)

    support = recent["low"].min()
    resistance = recent["high"].max()

    current_price = df["close"].iloc[-1]

    buy_points = 0
    sell_points = 0

    distance_support = abs(
        current_price - support
    )

    distance_resistance = abs(
        resistance - current_price
    )

    price_range = resistance - support

    if price_range <= 0:
        return 0, 0

    # Near support = possible bullish confirmation
    if distance_support / price_range < 0.20:
        buy_points = 8

    # Near resistance = possible bearish confirmation
    if distance_resistance / price_range < 0.20:
        sell_points = 8

    return buy_points, sell_points


# ============================================================
# SIGNAL ENGINE
# ============================================================

def calculate_signal(symbol):

    df = get_market_data(symbol)

    if df is None:
        return "NO SIGNAL", 0, [
            "Market data unavailable"
        ]

    try:

        df = calculate_indicators(df)

        current = df.iloc[-1]
        previous = df.iloc[-2]

        buy_score = 0
        sell_score = 0

        buy_confirmations = []
        sell_confirmations = []


        # ----------------------------------------------------
        # EMA TREND
        # ----------------------------------------------------

        if current["EMA20"] > current["EMA50"]:

            buy_score += 20
            buy_confirmations.append(
                "EMA20 above EMA50"
            )

        elif current["EMA20"] < current["EMA50"]:

            sell_score += 20
            sell_confirmations.append(
                "EMA20 below EMA50"
            )


        # ----------------------------------------------------
        # PRICE VS EMA20
        # ----------------------------------------------------

        if current["close"] > current["EMA20"]:

            buy_score += 10
            buy_confirmations.append(
                "Price above EMA20"
            )

        elif current["close"] < current["EMA20"]:

            sell_score += 10
            sell_confirmations.append(
                "Price below EMA20"
            )


        # ----------------------------------------------------
        # RSI
        # ----------------------------------------------------

        if 52 <= current["RSI"] <= 68:

            buy_score += 12
            buy_confirmations.append(
                "RSI bullish momentum"
            )

        elif 32 <= current["RSI"] <= 48:

            sell_score += 12
            sell_confirmations.append(
                "RSI bearish momentum"
            )


        # ----------------------------------------------------
        # CCI
        # ----------------------------------------------------

        if current["CCI"] > 50:

            buy_score += 12
            buy_confirmations.append(
                "CCI positive momentum"
            )

        elif current["CCI"] < -50:

            sell_score += 12
            sell_confirmations.append(
                "CCI negative momentum"
            )


        # ----------------------------------------------------
        # STOCHASTIC
        # ----------------------------------------------------

        if (
            current["STOCH_K"] >
            current["STOCH_D"]
        ):

            buy_score += 10
            buy_confirmations.append(
                "Stochastic bullish"
            )

        elif (
            current["STOCH_K"] <
            current["STOCH_D"]
        ):

            sell_score += 10
            sell_confirmations.append(
                "Stochastic bearish"
            )


        # ----------------------------------------------------
        # MACD
        # ----------------------------------------------------

        if (
            current["MACD"] >
            current["MACD_SIGNAL"]
        ):

            buy_score += 12
            buy_confirmations.append(
                "MACD bullish"
            )

        elif (
            current["MACD"] <
            current["MACD_SIGNAL"]
        ):

            sell_score += 12
            sell_confirmations.append(
                "MACD bearish"
            )


        # ----------------------------------------------------
        # CANDLE CONFIRMATION
        # ----------------------------------------------------

        candle_buy, candle_sell = candle_confirmation(df)

        buy_score += candle_buy
        sell_score += candle_sell

        if candle_buy:
            buy_confirmations.append(
                "Bullish candle confirmation"
            )

        if candle_sell:
            sell_confirmations.append(
                "Bearish candle confirmation"
            )


        # ----------------------------------------------------
        # SUPPORT / RESISTANCE
        # ----------------------------------------------------

        sr_buy, sr_sell = support_resistance(df)

        buy_score += sr_buy
        sell_score += sr_sell

        if sr_buy:
            buy_confirmations.append(
                "Price near support"
            )

        if sr_sell:
            sell_confirmations.append(
                "Price near resistance"
            )


        # ----------------------------------------------------
        # FINAL DECISION
        # ----------------------------------------------------

        total_possible = 88

        strongest_score = max(
            buy_score,
            sell_score
        )

        difference = abs(
            buy_score - sell_score
        )

        # Don't force a signal when the market is unclear.
        if strongest_score < 55:
            return "NO SIGNAL", strongest_score, [
                "Not enough confirmations"
            ]

        if difference < 12:
            return "NO SIGNAL", strongest_score, [
                "Market direction is conflicting"
            ]

        if buy_score > sell_score:

            return (
                "BUY 🟢",
                buy_score,
                buy_confirmations
            )

        return (
            "SELL 🔴",
            sell_score,
            sell_confirmations
        )

    except Exception as error:

        print("Signal engine error:", error)

        return "NO SIGNAL", 0, [
            "Analysis error"
        ]


# ============================================================
# START COMMAND
# ============================================================

@bot.message_handler(commands=["start"])
def main_menu(message):

    chat_id = message.chat.id

    get_session(chat_id)

    markup = InlineKeyboardMarkup()

    markup.add(
        InlineKeyboardButton(
            "🚀 Scan Market",
            callback_data="menu_signals"
        )
    )

    bot.send_message(
        chat_id,

        "🤖 *SMESH SIGNAL ENGINE v6*\n\n"
        "📊 *Mode:* Paper / Simulation\n"
        "🧠 *Engine:* Multi-Confirmation Analysis\n"
        "🛡️ *Random Signals:* Disabled\n\n"
        "Select an asset to start an analysis.",

        reply_markup=markup,
        parse_mode="Markdown"
    )


# ============================================================
# CALLBACKS
# ============================================================

@bot.callback_query_handler(
    func=lambda call: True
)
def callback_listener(call):

    chat_id = call.message.chat.id

    session = get_session(chat_id)

    bot.answer_callback_query(call.id)

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

        bot.send_message(
            chat_id,
            "💎 *SELECT ASSET:*",
            reply_markup=markup,
            parse_mode="Markdown"
        )

    elif call.data.startswith("pair_"):

        session["pair"] = call.data.replace(
            "pair_",
            ""
        )

        threading.Thread(
            target=run_analysis,
            args=(chat_id,)
        ).start()


# ============================================================
# ANALYSIS DISPLAY
# ============================================================

def run_analysis(chat_id):

    session = get_session(chat_id)

    symbol = session["pair"]

    wait_message = bot.send_message(
        chat_id,

        f"🔍 *Analyzing {symbol}...*\n\n"
        "🧠 Checking market structure\n"
        "📊 Checking indicators\n"
        "🕯️ Checking candle confirmation\n"
        "📍 Checking support/resistance\n\n"
        "⏳ Please wait...",

        parse_mode="Markdown"
    )

    time.sleep(2)

    try:
        bot.delete_message(
            chat_id,
            wait_message.message_id
        )
    except:
        pass

    signal, score, confirmations = calculate_signal(
        symbol
    )

    markup = InlineKeyboardMarkup()

    markup.add(
        InlineKeyboardButton(
            "🔄 Scan Again",
            callback_data="menu_signals"
        )
    )

    reason_text = "\n".join(
        f"• {item}"
        for item in confirmations
    )

    if signal == "NO SIGNAL":

        message_text = (
            "🛡️ *NO SIGNAL*\n\n"
            f"📊 *Asset:* {symbol}\n"
            f"🎯 *Technical Score:* {score}/88\n\n"
            "🧠 *Reason:*\n"
            f"{reason_text}\n\n"
            "⚠️ Market conditions are not strong enough "
            "for a reliable simulation entry."
        )

    else:

        message_text = (
            "🎯 *TECHNICAL SIMULATION SIGNAL*\n\n"
            f"📊 *Asset:* {symbol}\n"
            f"🎯 *Technical Score:* {score}/88\n"
            f"🚀 *Action:* *{signal}*\n\n"
            "🧠 *Confirmations:*\n"
            f"{reason_text}\n\n"
            "📌 Paper/simulation result only — "
            "not a guaranteed outcome."
        )

    bot.send_message(
        chat_id,
        message_text,
        reply_markup=markup,
        parse_mode="Markdown"
    )


# ============================================================
# START BOT
# ============================================================

print(
    "⚡ SMESH Signal Engine v6 "
    "started successfully."
)

bot.infinity_polling(
    skip_pending=True
)
