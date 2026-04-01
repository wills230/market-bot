import requests
import time
from datetime import datetime
import pytz

EASTERN = pytz.timezone("US/Eastern")

def now_et():
    return datetime.now(EASTERN)

# ============================================================
#  YOUR KEYS
# ============================================================
POLYGON_API_KEY = "bwmQrJUN3aF_2lL0iOSPsyObJNpLIZkX"
NTFY_CHANNEL    = "my-market-alerts"
# ============================================================

POLYGON_BASE = "https://api.polygon.io"
NTFY_BASE    = "https://ntfy.sh"

WATCHLIST = [
    # S&P 500 & Nasdaq 100 ETFs
    "SPY", "QQQ", "IVV", "VOO",

    # Mega cap tech
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA",
    "ORCL", "CRM", "ADBE", "AMD", "QCOM", "MU", "AVGO", "INTC",
    "NFLX", "PYPL", "CSCO",

    # Financials
    "JPM", "GS", "BAC", "MS", "WFC", "C", "BLK", "V", "MA", "AXP",

    # Healthcare
    "LLY", "UNH", "JNJ", "ABBV", "MRK", "PFE", "MRNA",
    "BIIB", "GILD", "REGN", "AMGN",

    # Energy
    "XOM", "CVX", "COP",

    # Industrials / defense
    "BA", "LMT", "RTX", "NOC", "GD", "CAT", "HON",

    # Consumer
    "HD", "MCD", "SBUX", "NKE", "COST",

    # Other
    "PLTR", "COIN",
]

VOLUME_SPIKE_MULTIPLIER = 2.5
PRICE_SPIKE_PERCENT     = 3.0
SCAN_INTERVAL_SECONDS   = 60 * 20   # 20 min — gives Polygon free tier breathing room
CLOSED_INTERVAL_SECONDS = 60 * 30   # 30 min when market is closed

daily_alerts    = []
last_recap_date = None
alerted_tickers = set()


# ── Helpers ───────────────────────────────────────────────────────────────────

def is_market_hours():
    now = now_et()
    if now.weekday() >= 5:
        return False
    market_open  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0,  second=0, microsecond=0)
    return market_open <= now <= market_close

def is_recap_time():
    now = now_et()
    if now.weekday() >= 5:
        return False
    return now.hour >= 16

def reset_daily_state():
    global daily_alerts, alerted_tickers
    daily_alerts    = []
    alerted_tickers = set()
    print(f"[{now_et().strftime('%I:%M %p ET')}] Daily state reset.")


# ── Notifications ─────────────────────────────────────────────────────────────

def send_alert(title, message, priority="default"):
    try:
        requests.post(
            f"{NTFY_BASE}/{NTFY_CHANNEL}",
            data=message.encode("utf-8"),
            headers={
                "Title":    title,
                "Priority": priority,
                "Tags":     "chart_increasing"
            },
            timeout=10
        )
        print(f"[ALERT SENT] {title}")
        daily_alerts.append({
            "time":  now_et().strftime("%I:%M %p"),
            "title": title
        })
    except Exception as e:
        print(f"[ALERT ERROR] {e}")


def send_daily_recap():
    global last_recap_date
    today = now_et().date()

    if last_recap_date == today:
        return

    print("\n[RECAP] Sending daily recap...")

    if not daily_alerts:
        send_alert(
            "Daily Recap — Quiet day",
            "Bot ran all day. No unusual volume or price signals today.",
            priority="low"
        )
    else:
        lines = [f"Signals today: {len(daily_alerts)}\n"]
        for a in daily_alerts:
            lines.append(f"  {a['time']} — {a['title']}")
        lines.append("\nCheck earlier alerts for full details.")
        send_alert(
            f"Daily Recap — {len(daily_alerts)} signal(s) today",
            "\n".join(lines),
            priority="high"
        )

    last_recap_date = today
    reset_daily_state()


# ── Market scanning ───────────────────────────────────────────────────────────

def get_stock_snapshot(ticker):
    try:
        url  = f"{POLYGON_BASE}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"
        r    = requests.get(url, params={"apiKey": POLYGON_API_KEY}, timeout=10)
        data = r.json()
        if "ticker" not in data:
            return None
        t = data["ticker"]
        return {
            "ticker":     ticker,
            "price":      t.get("day", {}).get("c", 0),
            "volume":     t.get("day", {}).get("v", 0),
            "avg_volume": t.get("prevDay", {}).get("v", 1),
            "change_pct": t.get("todaysChangePerc", 0),
        }
    except Exception as e:
        print(f"[POLYGON ERROR] {ticker}: {e}")
        return None


def check_ticker(ticker):
    snap = get_stock_snapshot(ticker)
    if not snap:
        return

    vol_ratio  = snap["volume"] / max(snap["avg_volume"], 1)
    change_pct = abs(snap["change_pct"])
    signals    = []

    if vol_ratio >= VOLUME_SPIKE_MULTIPLIER:
        signals.append(f"Volume {vol_ratio:.1f}x average")
    if change_pct >= PRICE_SPIKE_PERCENT:
        direction = "UP" if snap["change_pct"] > 0 else "DOWN"
        signals.append(f"Price {direction} {change_pct:.1f}%")

    if signals:
        is_urgent = len(signals) >= 2
        if ticker in alerted_tickers and not is_urgent:
            return
        alerted_tickers.add(ticker)

        title   = f"SIGNAL: {ticker} — {', '.join(signals)}"
        message = (
            f"{ticker} @ ${snap['price']:.2f}\n"
            f"Change:  {snap['change_pct']:+.2f}%\n"
            f"Volume:  {int(snap['volume']):,} ({vol_ratio:.1f}x avg)\n"
            f"Signal:  {', '.join(signals)}\n"
            f"Time:    {now_et().strftime('%I:%M %p ET')}"
        )
        priority = "urgent" if is_urgent else "high"
        send_alert(title, message, priority)


def run_scan():
    print(f"\n{'='*50}")
    print(f"  SCAN — {now_et().strftime('%I:%M %p ET')} [{len(WATCHLIST)} tickers]")
    for i, ticker in enumerate(WATCHLIST, 1):
        print(f"  [{i}/{len(WATCHLIST)}] {ticker}...")
        check_ticker(ticker)
    print(f"  Done. Next scan in 20 minutes.")


# ── Main loop ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Market Signal Bot starting up...")
    print(f"Watching {len(WATCHLIST)} tickers")
    print(f"Alerts going to ntfy channel: {NTFY_CHANNEL}")
    print("Daily recap sends after 4:00 PM ET every trading day\n")

    send_alert(
        "Market Bot Online",
        f"Scanner is live. Watching {len(WATCHLIST)} tickers.\nDaily recap after 4:00 PM ET.",
        priority="default"
    )

    while True:
        now = now_et()

        if is_recap_time():
            send_daily_recap()
            print(f"[{now.strftime('%I:%M %p ET')}] After hours — waiting 30 min...")
            time.sleep(CLOSED_INTERVAL_SECONDS)
            continue

        if is_market_hours():
            run_scan()
            time.sleep(SCAN_INTERVAL_SECONDS)
            continue

        print(f"[{now.strftime('%I:%M %p ET')}] Market closed — waiting 30 min...")
        time.sleep(CLOSED_INTERVAL_SECONDS)
