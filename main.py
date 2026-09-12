import os
import threading

import numpy as np
import pandas as pd
import ta
import telebot
import yfinance as yf
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing.")

bot = telebot.TeleBot(TOKEN)

user_sessions = {}
running_backtests = set()
backtest_lock = threading.Lock()


def get_session(chat_id):
    if chat_id not in user_sessions:
        user_sessions[chat_id] = {"pair": "EURUSD=X"}
    return user_sessions[chat_id]


def empty_results(error=None):
    return {
        "ok": error is None,
        "error": error or "",
        "actual_days": 0,
        "total_signals": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "buy_win_rate": 0.0,
        "sell_win_rate": 0.0,
        "gross_move_factor": 0.0,
        "avg_win_move": 0.0,
        "avg_loss_move": 0.0,
        "total_net_move": 0.0,
        "max_drawdown": 0.0,
        "max_win_streak": 0,
        "max_loss_streak": 0,
        "signals_per_day": 0.0,
        "dev_signals": 0,
        "dev_win_rate": 0.0,
        "oos_signals": 0,
        "oos_win_rate": 0.0,
    }


def clean_yfinance_data(df):
    if df is None or df.empty:
        raise ValueError("Yahoo Finance returned no data.")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            str(col[0]).strip()
            if isinstance(col, tuple)
            else str(col).strip()
            for col in df.columns
        ]

    df = df.reset_index()

    rename_map = {
        "Datetime": "time",
        "Date": "time",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
    }

    df.rename(columns=rename_map, inplace=True)

    required = ["time", "open", "high", "low", "close"]

    missing = [
        col for col in required
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required columns: {', '.join(missing)}"
        )

    df["time"] = pd.to_datetime(
        df["time"],
        errors="coerce",
        utc=True
    )

    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    df = (
        df.dropna(subset=required)
        .sort_values("time")
        .drop_duplicates(
            subset=["time"],
            keep="last"
        )
        .reset_index(drop=True)
    )

    if len(df) < 150:
        raise ValueError(
            f"Not enough valid candles after cleaning "
            f"({len(df)} available; 150 required)."
        )

    return df


def add_indicators(df):
    df = df.copy()

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

    macd = ta.trend.MACD(df["close"])

    df["MACD_DIFF"] = macd.macd_diff()

    df = df.dropna().reset_index(drop=True)

    if len(df) < 100:
        raise ValueError(
            "Not enough candles after indicator calculation."
        )

    return df


def calculate_signal(candle):
    buy_score = 0
    sell_score = 0

    if candle["EMA20"] > candle["EMA50"]:
        buy_score += 30

    if candle["RSI"] > 52:
        buy_score += 25

    if candle["CCI"] > 50:
        buy_score += 25

    if candle["MACD_DIFF"] > 0:
        buy_score += 30

    if candle["EMA20"] < candle["EMA50"]:
        sell_score += 30

    if candle["RSI"] < 48:
        sell_score += 25

    if candle["CCI"] < -50:
        sell_score += 25

    if candle["MACD_DIFF"] < 0:
        sell_score += 30

    final_score = max(
        buy_score,
        sell_score
    )

    score_gap = abs(
        buy_score - sell_score
    )

    if final_score < 85 or score_gap < 12:
        return (
            "NONE",
            final_score,
            buy_score,
            sell_score
        )

    if buy_score > sell_score:
        return (
            "BUY",
            buy_score,
            buy_score,
            sell_score
        )

    if sell_score > buy_score:
        return (
            "SELL",
            sell_score,
            buy_score,
            sell_score
        )

    return (
        "NONE",
        final_score,
        buy_score,
        sell_score
    )


def execute_simulation_slice(
    df,
    start_idx,
    end_idx
):
    journal = []

    i = max(0, start_idx)

    while i + 3 < end_idx:

        candle = df.iloc[i]

        (
            direction,
            score,
            buy_score,
            sell_score
        ) = calculate_signal(candle)

        if direction == "NONE":
            i += 1
            continue

        entry_idx = i + 1
        exit_idx = i + 3

        entry_price = float(
            df["open"].iloc[entry_idx]
        )

        exit_price = float(
            df["close"].iloc[exit_idx]
        )

        if direction == "BUY":
            signed_move = (
                exit_price - entry_price
            )
        else:
            signed_move = (
                entry_price - exit_price
            )

        if signed_move > 0:
            result = "WIN"
        elif signed_move < 0:
            result = "LOSS"
        else:
            result = "FLAT"

        journal.append({
            "time": df["time"].iloc[i],
            "direction": direction,
            "score": int(score),
            "buy_score": int(buy_score),
            "sell_score": int(sell_score),
            "entry": entry_price,
            "exit": exit_price,
            "result": result,
            "move": float(signed_move),
        })

        i += 4

    return journal


def calculate_metrics(
    full_journal,
    dev_journal,
    oos_journal,
    actual_days
):
    trades = [
        t for t in full_journal
        if t["result"] in ("WIN", "LOSS")
    ]

    if not trades:
        result = empty_results()

        result["actual_days"] = actual_days
        result["error"] = (
            "No qualifying trades were generated."
        )

        return result

    wins = [
        t for t in trades
        if t["result"] == "WIN"
    ]

    losses = [
        t for t in trades
        if t["result"] == "LOSS"
    ]

    buy_trades = [
        t for t in trades
        if t["direction"] == "BUY"
    ]

    sell_trades = [
        t for t in trades
        if t["direction"] == "SELL"
    ]

    buy_wins = [
        t for t in buy_trades
        if t["result"] == "WIN"
    ]

    sell_wins = [
        t for t in sell_trades
        if t["result"] == "WIN"
    ]

    gross_profit = sum(
        t["move"] for t in wins
    )

    gross_loss = sum(
        abs(t["move"])
        for t in losses
    )

    if gross_loss > 0:
        gross_move_factor = (
            gross_profit / gross_loss
        )
    else:
        gross_move_factor = (
            gross_profit
            if gross_profit > 0
            else 0.0
        )

    total_net_move = sum(
        t["move"]
        for t in trades
    )

    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0

    for trade in trades:

        equity += trade["move"]

        peak = max(
            peak,
            equity
        )

        max_drawdown = max(
            max_drawdown,
            peak - equity
        )

    max_win_streak = 0
    max_loss_streak = 0

    win_streak = 0
    loss_streak = 0

    for trade in trades:

        if trade["result"] == "WIN":

            win_streak += 1
            loss_streak = 0

            max_win_streak = max(
                max_win_streak,
                win_streak
            )

        else:

            loss_streak += 1
            win_streak = 0

            max_loss_streak = max(
                max_loss_streak,
                loss_streak
            )

    dev_trades = [
        t for t in dev_journal
        if t["result"] in ("WIN", "LOSS")
    ]

    oos_trades = [
        t for t in oos_journal
        if t["result"] in ("WIN", "LOSS")
    ]

    dev_wins = sum(
        t["result"] == "WIN"
        for t in dev_trades
    )

    oos_wins = sum(
        t["result"] == "WIN"
        for t in oos_trades
    )

    return {
        "ok": True,
        "error": "",
        "actual_days": int(actual_days),
        "total_signals": len(trades),
        "wins": len(wins),
        "losses": len(losses),

        "win_rate": round(
            len(wins) / len(trades) * 100,
            2
        ),

        "buy_win_rate": round(
            len(buy_wins)
            / len(buy_trades)
            * 100,
            2
        ) if buy_trades else 0.0,

        "sell_win_rate": round(
            len(sell_wins)
            / len(sell_trades)
            * 100,
            2
        ) if sell_trades else 0.0,

        "gross_move_factor": round(
            gross_move_factor,
            4
        ),

        "avg_win_move": round(
            np.mean([
                t["move"]
                for t in wins
            ]),
            6
        ) if wins else 0.0,

        "avg_loss_move": round(
            np.mean([
                abs(t["move"])
                for t in losses
            ]),
            6
        ) if losses else 0.0,

        "total_net_move": round(
            total_net_move,
            6
        ),

        "max_drawdown": round(
            max_drawdown,
            6
        ),

        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,

        "signals_per_day": round(
            len(trades) / actual_days,
            2
        ) if actual_days else 0.0,

        "dev_signals": len(dev_trades),

        "dev_win_rate": round(
            dev_wins / len(dev_trades) * 100,
            2
        ) if dev_trades else 0.0,

        "oos_signals": len(oos_trades),

        "oos_win_rate": round(
            oos_wins / len(oos_trades) * 100,
            2
        ) if oos_trades else 0.0,
    }


def run_advanced_backtest_v3_2(
    ticker_symbol
):
    try:

        df = yf.download(
            tickers=ticker_symbol,
            period="60d",
            interval="5m",
            progress=False,
            auto_adjust=False,
        )

        df = clean_yfinance_data(df)

        actual_days = (
            df["time"]
            .dt.date
            .nunique()
        )

        df = add_indicators(df)

        total_rows = len(df)

        split_idx = int(
            total_rows * 0.70
        )

        if (
            split_idx < 60
            or
            (total_rows - split_idx) < 10
        ):
            raise ValueError(
                "Insufficient data for a reliable 70/30 split."
            )

        dev_journal = execute_simulation_slice(
            df,
            0,
            split_idx
        )

        oos_journal = execute_simulation_slice(
            df,
            split_idx,
            total_rows
        )

        full_journal = (
            dev_journal +
            oos_journal
        )

        return calculate_metrics(
            full_journal,
            dev_journal,
            oos_journal,
            actual_days
        )

    except Exception as exc:

        print(
            f"Engine V3.2 error: {exc}"
        )

        return empty_results(
            str(exc)
        )


@bot.message_handler(
    commands=["start"]
)
def main_menu(message):

    chat_id = message.chat.id

    get_session(chat_id)

    markup = InlineKeyboardMarkup()

    markup.add(
        InlineKeyboardButton(
            "📈 Run Historical Backtest v3.2",
            callback_data="menu_backtest_v3_2",
        )
    )

    markup.add(
        InlineKeyboardButton(
            "🧑‍💻 System Support",
            url="https://t.me",
        )
    )

    bot.send_message(
        chat_id,

        "🤖 SMESH FOREX | "
        "ARCHIVAL AUDIT ENGINE v3.2\n\n"

        "📊 Status: Historical "
        "Backtest Operational\n"

        "🛡️ Mode: Historical / "
        "Paper Simulation\n"

        "🔍 Entry: i+1 Open | "
        "Exit: i+3 Close\n"

        "⚠️ Technical Threshold: "
        "85/110\n\n"

        "Select an option below:",

        reply_markup=markup,
    )


@bot.callback_query_handler(
    func=lambda call: True
)
def callback_listener(call):

    chat_id = call.message.chat.id

    session = get_session(chat_id)

    try:
        bot.answer_callback_query(
            call.id
        )
    except Exception:
        pass

    if call.data == "menu_backtest_v3_2":

        markup = InlineKeyboardMarkup()

        markup.row(
            InlineKeyboardButton(
                "EUR/USD",
                callback_data="pair_EURUSD=X"
            ),

            InlineKeyboardButton(
                "GBP/USD",
                callback_data="pair_GBPUSD=X"
            ),
        )

        markup.row(
            InlineKeyboardButton(
                "AUD/USD",
                callback_data="pair_AUDUSD=X"
            ),

            InlineKeyboardButton(
                "USD/CAD",
                callback_data="pair_USDCAD=X"
            ),
        )

        bot.send_message(
            chat_id,

            "💎 SELECT A FOREX ASSET "
            "FOR HISTORICAL AUDIT "
            "(5m candles):",

            reply_markup=markup,
        )

    elif call.data.startswith("pair_"):

        ticker = call.data.replace(
            "pair_",
            "",
            1
        )

        session["pair"] = ticker

        with backtest_lock:

            if chat_id in running_backtests:

                bot.send_message(
                    chat_id,

                    "⏳ A backtest is "
                    "already running for "
                    "this chat. Please wait."
                )

                return

            running_backtests.add(
                chat_id
            )

        thread = threading.Thread(
            target=process_backtest_v3,
            args=(chat_id,),
            daemon=True,
        )

        thread.start()


def process_backtest_v3(chat_id):

    try:

        session = get_session(
            chat_id
        )

        ticker = session["pair"]

        clean_name = ticker.replace(
            "=X",
            ""
        )

        wait_msg = bot.send_message(
            chat_id,

            f"📥 Downloading historical "
            f"data for {clean_name}...\n"

            "Running the backtest and "
            "calculating journal metrics... ⏳",
        )

        results = run_advanced_backtest_v3_2(
            ticker
        )

        try:

            bot.delete_message(
                chat_id,
                wait_msg.message_id
            )

        except Exception:
            pass

        markup = InlineKeyboardMarkup()

        markup.add(
            InlineKeyboardButton(
                "🔄 Audit Another Asset",
                callback_data="menu_backtest_v3_2",
            )
        )

        if not results.get(
            "ok",
            False
        ):

            error_text = results.get(
                "error",
                "Unknown data error."
            )

            bot.send_message(
                chat_id,

                "❌ BACKTEST ERROR\n\n"

                f"{error_text}\n\n"

                "Please try another asset "
                "or run the test again.",

                reply_markup=markup,
            )

            return

        bot.send_message(
            chat_id,

            f"📋 QUANTITATIVE AUDIT "
            f"JOURNAL ({clean_name}) 📋\n\n"

            f"📅 Data Dates: "
            f"{results['actual_days']}\n"

            f"⏱ Candle Interval: "
            f"5 Minutes\n\n"

            f"📊 Total Trades: "
            f"{results['total_signals']}\n"

            f"🟩 Wins: "
            f"{results['wins']}\n"

            f"🟥 Losses: "
            f"{results['losses']}\n\n"

            f"🎯 Historical Win Rate: "
            f"{results['win_rate']}%\n"

            f"🟢 BUY Win Rate: "
            f"{results['buy_win_rate']}%\n"

            f"🔴 SELL Win Rate: "
            f"{results['sell_win_rate']}%\n\n"

            f"💸 Gross Move Factor: "
            f"{results['gross_move_factor']}\n"

            f"📈 Average Win Move: "
            f"{results['avg_win_move']}\n"

            f"📉 Average Loss Move: "
            f"{results['avg_loss_move']}\n"

            f"💰 Total Net Move: "
            f"{results['total_net_move']}\n"

            f"📉 Move-Based Drawdown: "
            f"{results['max_drawdown']}\n"

            f"🔥 Max Winning Streak: "
            f"{results['max_win_streak']}\n"

            f"⚠️ Max Losing Streak: "
            f"{results['max_loss_streak']}\n"

            f"⚡ Signals/Day: "
            f"{results['signals_per_day']}\n\n"

            f"🧪 DEVELOPMENT "
            f"(In-Sample 70%)\n"

            f"• Trades: "
            f"{results['dev_signals']}\n"

            f"• Win Rate: "
            f"{results['dev_win_rate']}%\n\n"

            f"🧪 OUT-OF-SAMPLE "
            f"(Test 30%)\n"

            f"• Trades: "
            f"{results['oos_signals']}\n"

            f"• Win Rate: "
            f"{results['oos_win_rate']}%\n\n"

            "ℹ️ Note: Spread, slippage, "
            "swap, commission, position "
            "sizing and pip value are not "
            "included. This is historical "
            "price-move simulation only. "
            "Historical performance does "
            "not guarantee future results.",

            reply_markup=markup,
        )

    except Exception as exc:

        print(
            f"Telegram processing error: {exc}"
        )

        try:

            bot.send_message(
                chat_id,

                "❌ An unexpected error "
                "occurred while processing "
                "the backtest."
            )

        except Exception:
            pass

    finally:

        with backtest_lock:

            running_backtests.discard(
                chat_id
            )


if __name__ == "__main__":

    print(
        "⚡ SMESH FOREX V3.2 "
        "historical/paper backtest "
        "engine is running..."
    )

    bot.infinity_polling(
        skip_pending=True
)
