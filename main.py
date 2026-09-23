import os
import requests
import pandas as pd
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from datetime import datetime, timezone, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

from engine import run_ml_prediction
from renderer import draw_ai_chart

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Multi-TF AI Engine Operational")

threading.Thread(target=lambda: HTTPServer(("0.0.0.0", int(os.environ.get("PORT", 10000))), HealthCheckHandler).serve_forever(), daemon=True).start()

# Your API Keys are explicitly loaded here
TELEGRAM_TOKEN = "8802519909:AAEH7PkwM7kurbf7tBdiqo3vfDJsbkq-SK8"
TWELVE_DATA_API_KEY = "c279c8beeb634d958bf42a8cad0fa6ca"

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
    # Market Selection Menu
    kb = [
        [InlineKeyboardButton("EUR/USD", callback_data="asset_EURUSD"), InlineKeyboardButton("GBP/USD", callback_data="asset_GBPUSD")],
        [InlineKeyboardButton("USD/JPY", callback_data="asset_USDJPY"), InlineKeyboardButton("XAU/USD", callback_data="asset_XAUUSD")]
    ]
    await update.message.reply_text(
        "🧠 **MULTI-TIMEFRAME AI SCANNER** 🧠\n\nSelect a market to begin:",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    # Timeframe Selection Menu
    if data.startswith("asset_"):
        pair = data.split("_")[1]
        formatted = f"{pair[:3]}/{pair[3:]}"
        
        kb = [
            [InlineKeyboardButton("M1 (1-Minute) Stream", callback_data=f"tf_{pair}_1min")],
            [InlineKeyboardButton("M5 (5-Minute) Stream", callback_data=f"tf_{pair}_5min")],
            [InlineKeyboardButton("M15 (15-Minute) Stream", callback_data=f"tf_{pair}_15min")]
        ]
        await query.edit_message_text(
            f"Market locked: **{formatted}**\nSelect base timeframe for AI analysis:", 
            reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
        )
        return

    # Horizon Prediction Menu
    if data.startswith("tf_"):
        parts = data.split("_")
        pair = parts[1]
        tf = parts[2]
        formatted = f"{pair[:3]}/{pair[3:]}"
        
        if tf == "1min":
            kb = [
                [InlineKeyboardButton("Live Entry (Next 1m)", callback_data=f"h_{pair}_1min_1")],
                [InlineKeyboardButton("Upcoming Trade (Next 30m)", callback_data=f"h_{pair}_1min_30")],
                [InlineKeyboardButton("Upcoming Trade (Next 1h)", callback_data=f"h_{pair}_1min_60")]
            ]
        elif tf == "5min":
            kb = [
                [InlineKeyboardButton("Live Entry (Next 5m)", callback_data=f"h_{pair}_5min_1")],
                [InlineKeyboardButton("Upcoming Trade (Next 30m)", callback_data=f"h_{pair}_5min_6")],
                [InlineKeyboardButton("Upcoming Trade (Next 1h)", callback_data=f"h_{pair}_5min_12")]
            ]
        elif tf == "15min":
            kb = [
                [InlineKeyboardButton("Live Entry (Next 15m)", callback_data=f"h_{pair}_15min_1")],
                [InlineKeyboardButton("Upcoming Trade (Next 30m)", callback_data=f"h_{pair}_15min_2")],
                [InlineKeyboardButton("Upcoming Trade (Next 1h)", callback_data=f"h_{pair}_15min_4")]
            ]
            
        await query.edit_message_text(
            f"Market: **{formatted}** | Base: **{tf.upper()}**\nSelect target execution window:", 
            reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
        )
        return

    # Execution & Formatting
    if data.startswith("h_"):
        parts = data.split("_")
        pair = parts[1]
        tf = parts[2]
        horizon_bars = int(parts[3])
        
        formatted = f"{pair[:3]}/{pair[3:]}"
        interval_label = "M15" if tf == "15min" else ("M1" if tf == "1min" else "M5")
        mins_per_bar = 15 if tf == "15min" else (1 if tf == "1min" else 5)
        horizon_label = f"{horizon_bars * mins_per_bar}m"

        await query.edit_message_text(f"⚙️ Fetching **{interval_label}** stream for **{formatted}**...\n🧠 Training AI Model ({horizon_label} Forward-Looking)...")
        
        df = fetch_data(pair, interval=tf)
        if df is None: return await query.message.reply_text("❌ API connection failed.")

        signal_type, confidence, summary = run_ml_prediction(df, horizon_bars=horizon_bars, interval_label=interval_label)
        
        prob_up = confidence if "CALL" in signal_type else (100 - confidence if "PUT" in signal_type else 50.0)
        prob_down = confidence if "PUT" in signal_type else (100 - confidence if "CALL" in signal_type else 50.0)
        
        chart_bytes = draw_ai_chart(df, formatted, horizon_label, prob_up, prob_down, interval_label=interval_label)
        price = df.iloc[-1]['close']
        
        now_utc = datetime.now(timezone.utc)
        target_time = now_utc + timedelta(minutes=horizon_bars * mins_per_bar)
        
        str_now = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
        str_target = target_time.strftime("%Y-%m-%d %H:%M:%S UTC")

        if "NEUTRAL" in signal_type:
            msg = (
                f"⚪ **{interval_label} SCAN: NO CLEAR SETUP**\n\n"
                f"🏛 **Market:** {formatted} (Base: {interval_label})\n"
                f"💵 **Current Price:** `{price}`\n\n"
                f"🕒 **Current Scan Time:** `{str_now}`\n"
                f"🛡 **Diagnostic:** {summary}"
            )
        else:
            icon = "🟢" if "CALL" in signal_type else "🔴"
            msg = (
                f"{icon} **{signal_type}** {icon}\n\n"
                f"🏛 **Market:** {formatted} (Base: {interval_label})\n"
                f"🎯 **Model Certainty:** `{confidence}%`\n"
                f"💵 **Reference Price:** `{price}`\n\n"
                f"🕒 **Signal Issued At:**\n`{str_now}`\n\n"
                f"⏳ **TARGET TRADE TIME (Execute Over Next {horizon_label}):**\n`{str_target}`\n\n"
                f"🧠 **AI Diagnostic:** {summary}\n\n"
                f"👇 *Send /start to scan next.*"
            )

        await query.message.reply_photo(photo=chart_bytes, caption=msg, parse_mode="Markdown")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()
