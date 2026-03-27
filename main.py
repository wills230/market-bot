import requests
import time
from datetime import datetime, timedelta
import pytz

EASTERN = pytz.timezone("US/Eastern")

def now_et():
    return datetime.now(EASTERN)

# ============================================================
#  PASTE YOUR KEYS HERE — these are the only lines you touch
# ============================================================
POLYGON_API_KEY = "bwmQrJUN3aF_2lL0iOSPsyObJNpLIZkX"
NTFY_CHANNEL    = "my-market-alerts"
# ============================================================

POLYGON_BASE = "https://api.polygon.io"
EDGAR_BASE   = "https://efts.sec.gov"
NTFY_BASE    = "https://ntfy.sh"

WATCHLIST = [
    "AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA",
    "JPM","GS","BAC","XOM","CVX","LLY","UNH","BA",
    "AMD","MRNA","PFE","NFLX","V","CRM","ORCL","QCOM","MU",
    "BIIB","GILD","ABBV","REGN",
    "MS","WFC","C","BLK",
    "LMT","RTX","NOC","GD",
    "PLTR","COIN"
]

VOLUME_SPIKE_MULTIPLIER = 2.5
PRICE_SPIKE_PERCENT     = 3.0

daily_alerts     = []
recap_sent_today = False


def send_alert(title, message, priority="default"):
    try:
        requests.post(
            f"{NTFY_BASE}/{NTFY_CHANNEL}",
            data=message.encode("utf-8"),
            headers={
                "Title": title,
                "Priority": priority,
                "Tags": "chart_increasing"
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
    print("\n[RECAP] Sending daily recap...")
    if not daily_alerts:
        send_alert(
            "Daily Recap — Quiet day",
            "Bot ran all day and found no unusual signals. Markets were quiet today.",
            priority="low"
        )
    else:
        lines = [f"Signals caught today: {len(daily_alerts)}\n"]
        for a in daily_alerts:
            lines.append(f"  {a['time']} — {a['title']}")
        lines.append("\nCheck your earlier alerts for full details.")
        send_alert(
            f"Daily Recap — {len(daily_alerts)} signal(s) today",
            "\n".join(lines),
            priority="high"
        )
    daily_alerts.clear()


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


def check_volume_and_price(ticker):
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
        title   = f"SIGNAL: {ticker} — {', '.join(signals)}"
        message = (
            f"{ticker} @ ${snap['price']:.2f}\n"
            f"Change: {snap['change_pct']:+.2f}%\n"
            f"Volume: {int(snap['volume']):,} ({vol_ratio:.1f}x avg)\n"
            f"Signals: {', '.join(signals)}\n"
            f"Time: {now_et().strftime('%I:%M %p ET')}"
        )
        priority = "urgent" if len(signals) >= 2 else "high"
        send_alert(title, message, priority)


def check_sec_form4():
    try:
        today = now_et().strftime("%Y-%m-%d")
        url   = f"{EDGAR_BASE}/LATEST/search-index?q=%22form+4%22&dateRange=custom&startdt={today}&enddt={today}&forms=4"
        r     = requests.get(url, headers={"User-Agent": "MarketBot contact@example.com"}, timeout=15)
        data  = r.json()
        hits  = data.get("hits", {}).get("hits", [])
        if not hits:
            print("[EDGAR] No new Form 4 filings found")
            return
        for hit in hits[:20]:
            src         = hit.get("_source", {})
            entity_name = src.get("entity_name", "Unknown")
            filed_at    = src.get("file_date", today)
            for ticker in WATCHLIST:
                if ticker.lower() in entity_name.lower():
                    send_alert(
                        f"FORM 4 FILED: {ticker} insider activity",
                        f"New SEC Form 4 filing detected\nCompany: {entity_name}\nFiled: {filed_at}\nView: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=4\nTime: {now_et().strftime('%I:%M %p ET')}",
                        priority="high"
                    )
    except Exception as e:
        print(f"[EDGAR ERROR] {e}")


def check_congress_trades():
    try:
        url    = "https://house-stock-watcher-data.s3-us-east-2.amazonaws.com/data/all_transactions.json"
        r      = requests.get(url, timeout=15)
        trades = r.json()
        cutoff  = now_et() - timedelta(days=7)
        alerted = set()
        for t in trades:
            try:
                date = EASTERN.localize(datetime.strptime(t.get("transaction_date", ""), "%Y-%m-%d"))
                if date < cutoff:
                    continue
            except:
                continue
            ticker = t.get("ticker", "").upper().strip("$")
            if ticker in WATCHLIST and ticker not in alerted:
                alerted.add(ticker)
                send_alert(
                    f"CONGRESS TRADE: {ticker} — {t.get('type','Unknown')}",
                    f"Congressional trade on watchlist stock\nTicker: {ticker}\nMember: {t.get('representative','Unknown')}\nType: {t.get('type','Unknown')}\nAmount: {t.get('amount','Unknown')}\nDate: {t.get('transaction_date','Unknown')}\nSource: https://housestockwatcher.com",
                    priority="high"
                )
    except Exception as e:
        print(f"[CONGRESS ERROR] {e}")


def run_scan():
    print(f"\n{'='*50}\n  SCAN — {now_et().strftime('%I:%M %p ET')}\n{'='*50}")
    print(f"[1/3] Volume & price spikes ({len(WATCHLIST)} tickers)...")
    for ticker in WATCHLIST:
        check_volume_and_price(ticker)
        time.sleep(0.5)
    print("[2/3] SEC Form 4 filings...")
    check_sec_form4()
    print("[3/3] Congressional trades...")
    check_congress_trades()
    print("  Done. Next scan in 15 minutes.\n")


def is_market_hours():
    now     = now_et()
    weekday = now.weekday()
    if weekday >= 5:
        return False
    if now.hour < 9 or (now.hour == 9 and now.minute < 30):
        return False
    if now.hour >= 16:
        return False
    return True


def is_recap_time():
    now = now_et()
    return now.hour == 15 and now.minute >= 55


if __name__ == "__main__":
    print("Market Signal Bot starting up...")
    print(f"Watching {len(WATCHLIST)} tickers: {', '.join(WATCHLIST)}")
    print(f"Alerts going to ntfy channel: {NTFY_CHANNEL}")
    print("Daily recap sends at 3:55pm ET every trading day\n")

    send_alert(
        "Market Bot Online",
        f"Scanner is live. Watching {len(WATCHLIST)} tickers.\nDaily recap at 3:55pm ET.",
        priority="default"
    )

    while True:
        if is_market_hours():
            if is_recap_time() and not recap_sent_today:
                send_daily_recap()
                recap_sent_today = True
                time.sleep(60 * 10)
            else:
                if not is_recap_time():
                    recap_sent_today = False
                run_scan()
                time.sleep(60 * 15)
        else:
            recap_sent_today = False
            print(f"[{now_et().strftime('%I:%M %p ET')}] Market closed — waiting...")
            time.sleep(60 * 30)
