"""Generate 10 synthetic WealthPilot users with STOCK portfolios (NIFTY 100).

Each holding is a factual buy record: symbol, buy_date, quantity, buy_price.
Buy prices are drawn realistically from each stock's current price / 52-week
range (from corpus/nifty100_fundamentals.csv) so a later portfolio-summarizer
agent can compute plausible P&L. Fully synthetic — no real PII.

Outputs:
  data/profiles/users.json        # full profiles + nested holdings
  data/profiles/portfolios.csv    # flat holdings table (the "table" view)

Run:  python ingest/build_user_profiles.py
"""
import csv
import json
import os
import random
from datetime import date, timedelta

random.seed(42)  # reproducible

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUND = os.path.join(ROOT, "corpus", "nifty100_fundamentals.csv")
CONS = os.path.join(ROOT, "corpus", "nifty100_constituents.csv")
OUT_DIR = os.path.join(ROOT, "data", "profiles")
os.makedirs(OUT_DIR, exist_ok=True)

# Load current price + 52w range + sector for realistic buys
prices = {}
for r in csv.DictReader(open(FUND, encoding="utf-8")):
    try:
        prices[r["symbol"]] = {
            "price": float(r["price"]) if r["price"] else None,
            "lo": float(r["fifty_two_week_low"]) if r["fifty_two_week_low"] else None,
            "hi": float(r["fifty_two_week_high"]) if r["fifty_two_week_high"] else None,
        }
    except ValueError:
        pass
sector = {r["Symbol"]: r["Industry"] for r in csv.DictReader(open(CONS, encoding="utf-8-sig"))}
UNIVERSE = [s for s, p in prices.items() if p["price"]]

USERS = [
    # (id, name, age, risk, goals, crypto_cap_pct, monthly_invest_k)
    ("U001", "Marcus Chen", 34, "moderate", ["retirement", "house down-payment"], 5, 60),
    ("U002", "Priya Nair", 29, "aggressive", ["wealth creation"], 15, 45),
    ("U003", "Rajesh Kumar", 52, "conservative", ["capital preservation", "child education"], 0, 80),
    ("U004", "Aisha Khan", 41, "moderate", ["retirement", "travel fund"], 3, 55),
    ("U005", "Vikram Rao", 38, "aggressive", ["early retirement (FIRE)"], 20, 70),
    ("U006", "Sunita Desai", 47, "conservative", ["retirement", "healthcare buffer"], 0, 40),
    ("U007", "Arjun Mehta", 26, "aggressive", ["wealth creation", "starting a business"], 25, 30),
    ("U008", "Deepa Iyer", 35, "moderate", ["child education", "home renovation"], 5, 50),
    ("U009", "Farhan Ali", 44, "moderate", ["retirement"], 2, 65),
    ("U010", "Lakshmi Menon", 58, "conservative", ["retirement income", "legacy"], 0, 35),
]

RISK_HOLDINGS = {"conservative": (4, 6), "moderate": (5, 8), "aggressive": (6, 10)}
TODAY = date(2026, 7, 10)
START = date(2023, 1, 1)


def rand_date():
    days = (TODAY - START).days
    return (START + timedelta(days=random.randint(0, days - 30))).isoformat()


def buy_price(sym):
    p = prices[sym]
    lo = p["lo"] or p["price"] * 0.7
    # bought somewhere between ~30% below and ~10% above today's price, within reason
    low = max(lo * 0.9, p["price"] * 0.55)
    high = min(p["price"] * 1.12, (p["hi"] or p["price"]) * 1.02)
    return round(random.uniform(low, high), 2)


def make_holdings(risk):
    n = random.randint(*RISK_HOLDINGS[risk])
    picks = random.sample(UNIVERSE, n)
    holdings = []
    for sym in picks:
        bp = buy_price(sym)
        invest = random.uniform(15000, 220000)  # rupee value per position
        qty = max(1, round(invest / bp))
        holdings.append({
            "symbol": sym,
            "sector": sector.get(sym, ""),
            "buy_date": rand_date(),
            "quantity": qty,
            "buy_price": bp,
        })
    return sorted(holdings, key=lambda h: h["buy_date"])


def main():
    profiles = []
    for uid, name, age, risk, goals, crypto, invest_k in USERS:
        profiles.append({
            "user_id": uid,
            "name": name,
            "age": age,
            "risk_tolerance": risk,
            "goals": goals,
            "preferences": {"crypto_cap_pct": crypto, "base_currency": "INR"},
            "monthly_investment_inr": invest_k * 1000,
            "created": rand_date(),
            "holdings": make_holdings(risk),
        })

    with open(os.path.join(OUT_DIR, "users.json"), "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2, ensure_ascii=False)

    with open(os.path.join(OUT_DIR, "portfolios.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "user_name", "risk_tolerance", "symbol", "sector",
                    "buy_date", "quantity", "buy_price", "invested_value"])
        for p in profiles:
            for h in p["holdings"]:
                w.writerow([p["user_id"], p["name"], p["risk_tolerance"], h["symbol"],
                            h["sector"], h["buy_date"], h["quantity"], h["buy_price"],
                            round(h["quantity"] * h["buy_price"], 2)])

    tot_positions = sum(len(p["holdings"]) for p in profiles)
    print(f"wrote {len(profiles)} users, {tot_positions} positions")
    print("  ->", os.path.join(OUT_DIR, "users.json"))
    print("  ->", os.path.join(OUT_DIR, "portfolios.csv"))


if __name__ == "__main__":
    main()
