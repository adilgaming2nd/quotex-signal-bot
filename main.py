import os
import requests
import pandas as pd
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from datetime import datetime, timedelta
import zoneinfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

from engine import run_ml_prediction
from renderer import draw_ai_chart

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"AI Engine Operational")

threading.Thread(target=lambda: HTTPServer(("0.0.0.0", int(os.environ.get("PORT", 10000))), HealthCheckHandler).serve_forever(), daemon=True).start()

TELEGRAM_TOKEN = "8802519909:AAEH7PkwM7kurbf7tBdiqo3vfDJsbkq-SK8"
TWELVE_DATA_API_KEY = "c279c8beeb634d958bf42a8cad0fa6ca"

# Set your exact local timezone (UTC+6)
LOCAL_TZ = zoneinfo.ZoneInfo("Asia/Dhaka")

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

def fetch_data(pair, interval="5min"):
    try:
        url = f"https://api.twelvedata.com/time_series?symbol={pair[:3]}/{pair[3:]}&interval={interval}&outputsize=250&apikey={TWELVE_DATA_API_KEY}"
        data = requests.get(url, timeout=8).json()
        if "values" not in data: return None
        df = pd.DataFrame(data['values']).iloc[::-1].reset_index(drop=True)
        for col in ['open', 'high', 'low', 'close']: df[col] = df[col].astype(float)
        return df
    except: return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("EUR/USD", callback_data="asset_EURUSD"), InlineKeyboardButton("GBP/USD", callback_data="asset_GBPUSD")],
        [InlineKeyboardButton("USD/JPY", callback_data="asset_USDJPY"), InlineKeyboardButton("XAU/USD", callback_data="asset_XAUUSD")]
    ]
    await update.message.reply_text(
        "📊 **SELECT MARKET TO SCAN:**",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data.startswith("asset_"):
        pair = data.split("_")[1]
        formatted = f"{pair[:3]}/{pair[3:]}"
        
        kb = [
            [InlineKeyboardButton("⚡ 1-Minute Trade", callback_data=f"h_{pair}_1min_1")],
            [InlineKeyboardButton("⏱ 5-Minute Trade", callback_data=f"h_{pair}_5min_1")],
            [InlineKeyboardButton("⌛ 15-Minute Trade", callback_data=f"h_{pair}_15min_1")],
            [InlineKeyboardButton("📅 30-Minute Trade", callback_data=f"h_{pair}_5min_6")],
            [InlineKeyboardButton("🕐 1-Hour Trade", callback_data=f"h_{pair}_5min_12")]
        ]
        await query.edit_message_text(
            f"Market: **{formatted}**\nSelect your preferred trade length:", 
            reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
        )
        return

    if data.startswith("h_"):
        parts = data.split("_")
        pair = parts[1]
        tf = parts[2]
        horizon_bars = int(parts[3])
        
        formatted = f"{pair[:3]}/{pair[3:]}"
        interval_label = "M15" if tf == "15min" else ("M1" if tf == "1min" else "M5")
        mins_per_bar = 15 if tf == "15min" else (1 if tf == "1min" else 5)
        trade_duration_mins = horizon_bars * mins_per_bar

        await query.edit_message_text(f"🔍 Scanning **{formatted}**...")
        
        df = fetch_data(pair, interval=tf)
        if df is None: return await query.message.reply_text("❌ Connection failed. Try again.")

        signal_type, confidence, summary = run_ml_prediction(df, horizon_bars=horizon_bars, interval_label=interval_label)
        
        prob_up = confidence if "CALL" in signal_type else (100 - confidence if "PUT" in signal_type else 50.0)
        prob_down = confidence if "PUT" in signal_type else (100 - confidence if "CALL" in signal_type else 50.0)
        
        chart_bytes = draw_ai_chart(df, formatted, f"{trade_duration_mins}m", prob_up, prob_down, interval_label=interval_label)
        
        # Calculate Local Execution Times (Asia/Dhaka - UTC+6)
        now_local = datetime.now(LOCAL_TZ)
        expiry_local = now_local + timedelta(minutes=trade_duration_mins)
        
        start_time_str = now_local.strftime("%I:%M:%S %p")
        expiry_time_str = expiry_local.strftime("%I:%M:%S %p")

        if "NEUTRAL" in signal_type:
            msg = (
                f"⚪ **NO CLEAR SETUP DETECTED**\n\n"
                f"🏛 Market: **{formatted}**\n"
                f"🛡 Market is currently ranging or low probability. Please try another pair or timeframe."
            )
        else:
            is_up = "CALL" in signal_type
            direction_text = "🟢 CALL / UP" if is_up else "🔴 PUT / DOWN"
            
            msg = (
                f"🎯 **NEW SIGNAL READY**\n\n"
                f"🏛 **Market:** {formatted}\n"
                f"📈 **Direction:** {direction_text}\n"
                f"⏱ **Trade Duration:** `{trade_duration_mins} Minutes`\n"
                f"🔥 **Win Probability:** `{confidence}%`\n\n"
                f"📌 **WHAT TO DO ON QUOTEX:**\n"
                f"1️⃣ Open **{formatted}** on Quotex.\n"
                f"2️⃣ Set Trade Time to **`{trade_duration_mins} min`** (or target clock time **`{expiry_time_str}`**).\n"
                f"3️⃣ Press **{'GREEN (UP)' if is_up else 'RED (DOWN)'}** NOW (`{start_time_str}`).\n\n"
                f"👇 *Send /start for next trade.*"
            )

        await query.message.reply_photo(photo=chart_bytes, caption=msg, parse_mode="Markdown")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()
