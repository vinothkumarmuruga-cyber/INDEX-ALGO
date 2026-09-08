"""
Nifty CE/PE BEP Levels — Live Entry/Target/SL Journal (Streamlit + Upstox v3)
==============================================================================

Reproduces, live, the level/entry table you sketched:

    NIFTY OPEN | STRIKE CE | UP1 UP2 UP3 UP4 | DN1 DN2 DN3 DN4
    23747      |   23750   |
               | STRIKE PE | UP1 UP2 UP3 UP4 | DN1 DN2 DN3 DN4
               |   23750   |

Nearby strike = today's NIFTY open rounded to the strike step. UPn/DNn are
the "average of two option closes" BEP-style calc, cross-leg per your
corrected table (each leg's levels are priced against the OTHER leg's
option at the offset strike, not more of the same leg):

    CE UPn = (close of ATM CE + close of PE at strike+n*step) / 2
    CE DNn = (close of ATM CE + close of PE at strike-n*step) / 2
    PE UPn = (close of ATM PE + close of CE at strike-n*step) / 2
    PE DNn = (close of ATM PE + close of CE at strike+n*step) / 2

ENTRY LOGIC (as you described):
    Bullish (CE) entry -> CE closes (3-min TF) above CE-UP1  AND, same bar,
                           PE is below PE-DN1.
                           Target = CE-UP2 (next line up). SL = that CE
                           candle's low.
    Bearish (PE) entry -> vice versa: PE closes above PE-UP1 AND CE is
                           below CE-DN1.
                           Target = PE-UP2. SL = that PE candle's low.
    Laddered: the same check runs at UP2 (target UP3) and UP3 (target UP4)
              too, so a trade can also start off a UP2/UP3 breakout.

This is SIGNAL-ONLY — it does not place orders. You confirmed that in the
requirements. Paste your Upstox v3 access token in the sidebar; it must be
regenerated daily via Upstox's login flow (not handled by this app).

NOTE: Upstox endpoint paths/params are current as of Sep 2026 per Upstox's
own developer docs. If Upstox changes them, the three functions in the
"Upstox API" section below are the only place you need to touch.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Nifty CE/PE BEP Levels", layout="wide")

BASE_URL = "https://api.upstox.com"

UNDERLYING_MAP = {
    "NIFTY": ("NSE_INDEX|Nifty 50", 50),
    "BANKNIFTY": ("NSE_INDEX|Nifty Bank", 100),
    "FINNIFTY": ("NSE_INDEX|Nifty Fin Service", 50),
    "MIDCPNIFTY": ("NSE_INDEX|NIFTY MID SELECT", 25),
}

OFFSETS = [1, 2, 3, 4]  # UP1..UP4 / DN1..DN4 (multiplied by strike step)


# ======================================================================
# Upstox API
# ======================================================================

def _headers(token: str) -> dict:
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }


def fetch_nifty_open(underlying_key: str, token: str) -> float:
    """Today's opening price for the underlying index."""
    url = f"{BASE_URL}/v3/market-quote/ohlc"
    params = {"instrument_key": underlying_key, "interval": "1d"}
    r = requests.get(url, headers=_headers(token), params=params, timeout=10)
    r.raise_for_status()
    data = r.json().get("data", {})
    if not data:
        raise ValueError("Empty OHLC response for underlying — market may be closed / bad token.")
    first = next(iter(data.values()))
    return float(first["live_ohlc"]["open"])


@st.cache_data(ttl=600, show_spinner=False)
def fetch_option_contracts(underlying_key: str, expiry_str: str, token: str) -> pd.DataFrame:
    url = f"{BASE_URL}/v2/option/contract"
    params = {"instrument_key": underlying_key, "expiry_date": expiry_str}
    r = requests.get(url, headers=_headers(token), params=params, timeout=10)
    r.raise_for_status()
    data = r.json().get("data", [])
    return pd.DataFrame(data)


def build_strike_map(contracts_df: pd.DataFrame) -> dict:
    """(strike, 'CE'/'PE') -> instrument_key"""
    m = {}
    for _, row in contracts_df.iterrows():
        try:
            m[(int(round(float(row["strike_price"]))), row["instrument_type"])] = row["instrument_key"]
        except Exception:
            continue
    return m


def fetch_intraday_candles(instrument_key: str, token: str, interval_minutes: int) -> pd.DataFrame:
    url = f"{BASE_URL}/v3/historical-candle/intraday/{instrument_key}/minutes/{interval_minutes}"
    r = requests.get(url, headers=_headers(token), timeout=10)
    r.raise_for_status()
    candles = r.json().get("data", {}).get("candles", [])
    cols = ["timestamp", "open", "high", "low", "close", "volume", "oi"]
    df = pd.DataFrame(candles, columns=cols)
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df[["timestamp", "open", "high", "low", "close"]].sort_values("timestamp").reset_index(drop=True)


def fetch_many_candles(instrument_keys: dict, token: str, interval_minutes: int) -> dict:
    out = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {
            ex.submit(fetch_intraday_candles, ik, token, interval_minutes): name
            for name, ik in instrument_keys.items()
        }
        for fut in futures:
            name = futures[fut]
            try:
                out[name] = fut.result()
            except Exception as e:
                out[name] = pd.DataFrame()
                st.warning(f"Candle fetch failed for {name}: {e}")
    return out


# ======================================================================
# BEP level calculation (mirrors the Pine script's average-of-two-closes)
# ======================================================================

def compute_levels(candles: dict, strike_step: int) -> pd.DataFrame:
    """
    candles keys expected: 'CE_0' (ATM), 'CE_+1'..'CE_+4', 'CE_-1'..'CE_-4',
    and the same with 'PE_' prefix. Returns one row per 3-min bar with
    columns: timestamp, ce_close, ce_low, pe_close, pe_low,
    ce_up1..4, ce_dn1..4, pe_up1..4, pe_dn1..4

    Per your table, each leg's levels are built against the OTHER leg's
    option at the offset strike (this is what a strangle/BEP combo actually
    prices), not against more of the same leg:

        CE-UPn = avg(ATM CE close, PE close at strike + n*step)   <- PE strike ABOVE atm
        CE-DNn = avg(ATM CE close, PE close at strike - n*step)   <- PE strike BELOW atm
        PE-UPn = avg(ATM PE close, CE close at strike - n*step)   <- CE strike BELOW atm
        PE-DNn = avg(ATM PE close, CE close at strike + n*step)   <- CE strike ABOVE atm
    """
    ce0 = candles.get("CE_0", pd.DataFrame())
    pe0 = candles.get("PE_0", pd.DataFrame())
    if ce0.empty or pe0.empty:
        return pd.DataFrame()

    merged = ce0[["timestamp", "close", "low"]].rename(columns={"close": "ce_close", "low": "ce_low"})
    merged = merged.merge(
        pe0[["timestamp", "close", "low"]].rename(columns={"close": "pe_close", "low": "pe_low"}),
        on="timestamp", how="inner",
    )

    # (result column, base-leg column, other-leg candle key)
    spec = []
    for n in OFFSETS:
        spec.append((f"ce_up{n}", "ce_close", f"PE_+{n}"))
        spec.append((f"ce_dn{n}", "ce_close", f"PE_-{n}"))
        spec.append((f"pe_up{n}", "pe_close", f"CE_-{n}"))
        spec.append((f"pe_dn{n}", "pe_close", f"CE_+{n}"))

    for out_col, base_col, candle_key in spec:
        leg_df = candles.get(candle_key, pd.DataFrame())
        if leg_df.empty:
            merged[out_col] = float("nan")
            continue
        tmp_col = f"__{out_col}_leg"
        merged = merged.merge(
            leg_df[["timestamp", "close"]].rename(columns={"close": tmp_col}),
            on="timestamp", how="left",
        )
        merged[out_col] = (merged[base_col] + merged[tmp_col]) / 2

    merged = merged.drop(columns=[c for c in merged.columns if c.startswith("__")])
    return merged.sort_values("timestamp").reset_index(drop=True)


# ======================================================================
# Entry / Target / SL journal engine
# ======================================================================

def _crossed_up(prev_close, prev_line, close, line):
    if pd.isna(prev_close) or pd.isna(prev_line) or pd.isna(close) or pd.isna(line):
        return False
    return prev_close <= prev_line and close > line


def _try_open(side, other, tag, prev_row, row):
    """Look for a fresh close-above-UPn crossover (n=1..3) confirmed by the other
    leg sitting below its DN1. Only the first level that freshly crosses this bar
    is considered (matches one signal per bar)."""
    for n in OFFSETS[:-1]:  # UP1..UP3 -> target UP(n+1); UP4 has no UP5 to chain to
        if _crossed_up(prev_row[f"{side}_close"], prev_row[f"{side}_up{n}"],
                        row[f"{side}_close"], row[f"{side}_up{n}"]):
            if row[f"{other}_close"] < row[f"{other}_dn1"]:
                return {
                    "time": row["timestamp"], "side": tag,
                    "line": f"{side.upper()}-UP{n}", "entry": row[f"{side}_close"],
                    "target": row[f"{side}_up{n + 1}"], "target_n": n + 1,
                    "sl": row[f"{side}_low"], "exit": None, "result": "In Trade",
                }
            return None  # crossed but not confirmed by the other leg -> no entry this bar
    return None


def _try_chain(side, trade, row):
    """Target just hit = price already closed above that line, i.e. the next
    level's breakout condition. Roll straight into it without re-checking the
    other leg's confirmation (same trade, riding the ladder up)."""
    n = trade["target_n"]
    if n >= OFFSETS[-1]:  # UP4 hit -> top of the ladder, cycle ends here
        return None
    new_n = n + 1
    return {
        "time": row["timestamp"], "side": trade["side"],
        "line": f"{side.upper()}-UP{n} (chain)", "entry": row[f"{side}_close"],
        "target": row[f"{side}_up{new_n}"], "target_n": new_n,
        "sl": row[f"{side}_low"], "exit": None, "result": "In Trade",
    }


def build_journal(df: pd.DataFrame, max_rows: int) -> pd.DataFrame:
    if df.empty or len(df) < 2:
        return pd.DataFrame()

    journal = []
    open_ce = None  # dict: entry/target/target_n/sl/... or None
    open_pe = None

    prev = None
    for _, row in df.iterrows():
        if prev is not None:
            # ---- CE (bullish) side: CE breaks UPn while PE sits below PE-DN1 ----
            if open_ce is None:
                new_trade = _try_open("ce", "pe", "CE (Bullish)", prev, row)
                if new_trade:
                    open_ce = new_trade
                    journal.append(open_ce)
            else:
                if row["ce_low"] <= open_ce["sl"]:
                    open_ce["exit"], open_ce["result"] = row["ce_low"], "SL Hit"
                    open_ce = None
                elif not pd.isna(open_ce["target"]) and row["ce_close"] >= open_ce["target"]:
                    open_ce["exit"], open_ce["result"] = row["ce_close"], "Target Hit"
                    chained = _try_chain("ce", open_ce, row)
                    open_ce = chained
                    if chained:
                        journal.append(chained)

            # ---- PE (bearish) side: PE breaks UPn while CE sits below CE-DN1 ----
            if open_pe is None:
                new_trade = _try_open("pe", "ce", "PE (Bearish)", prev, row)
                if new_trade:
                    open_pe = new_trade
                    journal.append(open_pe)
            else:
                if row["pe_low"] <= open_pe["sl"]:
                    open_pe["exit"], open_pe["result"] = row["pe_low"], "SL Hit"
                    open_pe = None
                elif not pd.isna(open_pe["target"]) and row["pe_close"] >= open_pe["target"]:
                    open_pe["exit"], open_pe["result"] = row["pe_close"], "Target Hit"
                    chained = _try_chain("pe", open_pe, row)
                    open_pe = chained
                    if chained:
                        journal.append(chained)

        prev = row

    if not journal:
        return pd.DataFrame()
    jdf = pd.DataFrame(journal)
    if max_rows:
        jdf = jdf.tail(max_rows)
    return jdf.iloc[::-1].reset_index(drop=True)  # newest first


def style_result(val):
    color = {"In Trade": "#FFE58A", "Target Hit": "#B7EB8F", "SL Hit": "#FFA39E"}.get(val, "")
    return f"background-color: {color}" if color else ""


# ======================================================================
# Sidebar
# ======================================================================

with st.sidebar:
    st.subheader("Upstox")
    access_token = st.text_input("Access Token", type="password", help="Today's Upstox v3 access token")

    st.subheader("Contract Setup")
    symbol = st.selectbox("Symbol", list(UNDERLYING_MAP.keys()), index=0)
    default_key, default_step = UNDERLYING_MAP[symbol]
    underlying_key = st.text_input("Underlying Instrument Key", value=default_key)
    strike_step = st.number_input("Strike Step", value=default_step, step=1, min_value=1)
    expiry = st.date_input("Expiry Date", value=date.today() + timedelta(days=(3 - date.today().weekday()) % 7))

    st.subheader("Signal Settings")
    entry_tf = st.selectbox("Entry Timeframe (minutes)", [1, 3, 5, 10, 15], index=1)
    max_rows = st.number_input("Max Rows in Journal", value=20, min_value=1, max_value=200)
    refresh_secs = st.number_input("Auto-refresh (seconds)", value=30, min_value=10, max_value=300, step=5)

st.title("Nifty CE/PE BEP Levels — Live Entry / Target / SL")

if not access_token:
    st.info("Enter your Upstox access token in the sidebar to begin.")
    st.stop()


# ======================================================================
# Live panel (auto-refreshing)
# ======================================================================

@st.fragment(run_every=f"{int(refresh_secs)}s")
def live_panel():
    try:
        nifty_open = fetch_nifty_open(underlying_key, access_token)
    except Exception as e:
        st.error(f"Could not fetch {symbol} open price: {e}")
        return

    atm_strike = int(round(nifty_open / strike_step) * strike_step)

    try:
        contracts_df = fetch_option_contracts(underlying_key, expiry.strftime("%Y-%m-%d"), access_token)
    except Exception as e:
        st.error(f"Could not fetch option contracts: {e}")
        return
    if contracts_df.empty:
        st.error("No option contracts returned — check expiry date / underlying instrument key.")
        return
    strike_map = build_strike_map(contracts_df)

    # resolve the instrument keys we need: ATM +/- 1..4 steps, both CE & PE
    needed = {}
    missing = []
    for side in ("CE", "PE"):
        for n in [0] + OFFSETS + [-o for o in OFFSETS]:
            strike = atm_strike + n * strike_step
            key = strike_map.get((strike, side))
            label = f"{side}_0" if n == 0 else f"{side}_{'+' if n > 0 else ''}{n}"
            if key is None:
                missing.append(f"{side} {strike}")
            else:
                needed[label] = key

    if missing:
        st.warning("Missing contracts for: " + ", ".join(missing) + " — those levels will show blank.")

    candles = fetch_many_candles(needed, access_token, int(entry_tf))
    levels_df = compute_levels(candles, strike_step)

    st.caption(
        f"{symbol} open: **{nifty_open:.2f}** → nearby strike **{atm_strike}** "
        f"({entry_tf}-min candles, refreshing every {int(refresh_secs)}s)"
    )

    if levels_df.empty:
        st.warning("No overlapping candle data yet for the selected strikes — try again in a moment.")
        return

    last = levels_df.iloc[-1]

    # ---- levels table, laid out like your sketch ----
    def level_row(prefix, label):
        return {
            "": label,
            "UP1": last.get(f"{prefix}_up1"), "UP2": last.get(f"{prefix}_up2"),
            "UP3": last.get(f"{prefix}_up3"), "UP4": last.get(f"{prefix}_up4"),
            "DN1": last.get(f"{prefix}_dn1"), "DN2": last.get(f"{prefix}_dn2"),
            "DN3": last.get(f"{prefix}_dn3"), "DN4": last.get(f"{prefix}_dn4"),
        }

    levels_table = pd.DataFrame([
        level_row("ce", f"STRIKE CE {atm_strike} (close {last['ce_close']:.2f})"),
        level_row("pe", f"STRIKE PE {atm_strike} (close {last['pe_close']:.2f})"),
    ]).set_index("")
    st.dataframe(levels_table.style.format("{:.2f}"), use_container_width=True)

    # ---- journal ----
    journal_df = build_journal(levels_df, int(max_rows))
    st.subheader("Entry / Target / SL Journal")
    if journal_df.empty:
        st.caption("No signals yet today.")
    else:
        display_df = journal_df.rename(columns={
            "time": "Time", "side": "Side", "line": "Line",
            "entry": "Entry", "target": "Target", "sl": "SL",
            "exit": "Exit", "result": "Result",
        })
        display_df["Time"] = pd.to_datetime(display_df["Time"]).dt.strftime("%H:%M")
        for c in ["Entry", "Target", "SL", "Exit"]:
            display_df[c] = display_df[c].map(lambda v: "-" if pd.isna(v) else f"{v:.2f}")
        st.dataframe(
            display_df.style.applymap(style_result, subset=["Result"]),
            use_container_width=True, hide_index=True,
        )

    st.caption(f"Last updated: {pd.Timestamp.now(tz='Asia/Kolkata').strftime('%H:%M:%S')}")


live_panel()
