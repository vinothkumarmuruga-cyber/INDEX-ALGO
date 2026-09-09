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
from datetime import date, time as dtime, timedelta

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Nifty CE/PE BEP Levels", layout="wide")

BASE_URL = "https://api.upstox.com"

OFFSETS = [1, 2, 3, 4]  # UP1..UP4 / DN1..DN4 (multiplied by strike step)

# One tab per index. expiry_weekday: 0=Mon .. 6=Sun. monthly_only=True means
# only the last occurrence of that weekday in the month trades (matches
# NSE/BSE's current 2026 schedule: NIFTY weekly Tue, SENSEX weekly Thu,
# BANKNIFTY monthly-only, last Tuesday -- verify against Upstox/NSE if this
# changes again, it's only used to prefill the expiry date picker below).
# lot_size defaults are current as of Sep 2026 (NSE/BSE revise these periodically
# -- overridable per tab below, check the exchange circular if a PnL looks off).
TAB_CONFIGS = {
    "NIFTY": {"tag": "NIFTY", "underlying_key": "NSE_INDEX|Nifty 50", "strike_step": 50,
              "expiry_weekday": 1, "monthly_only": False, "lot_size": 65},
    "BANKNIFTY": {"tag": "BN", "underlying_key": "NSE_INDEX|Nifty Bank", "strike_step": 100,
                  "expiry_weekday": 1, "monthly_only": True, "lot_size": 30},
    "SENSEX": {"tag": "SENSEX", "underlying_key": "BSE_INDEX|SENSEX", "strike_step": 100,
               "expiry_weekday": 3, "monthly_only": False, "lot_size": 20},
}


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    first_next = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    d = first_next - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def default_expiry(weekday: int, monthly_only: bool) -> date:
    today = date.today()
    if not monthly_only:
        return today + timedelta(days=(weekday - today.weekday()) % 7)
    d = _last_weekday_of_month(today.year, today.month, weekday)
    if d < today:  # this month's last occurrence already passed -> roll to next month
        y, m = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
        d = _last_weekday_of_month(y, m, weekday)
    return d


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
    df = df[["timestamp", "open", "high", "low", "close"]].sort_values("timestamp")
    # guard against Upstox ever returning a duplicate/re-stated bar for the same
    # timestamp (would otherwise fan out row counts across the per-leg merges in
    # compute_levels and misalign which candle's low/high a check is really using)
    df = df.drop_duplicates(subset="timestamp", keep="last")
    return df.reset_index(drop=True)


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
    columns: timestamp, ce_close, ce_high, ce_low, pe_close, pe_high, pe_low,
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

    merged = ce0[["timestamp", "close", "high", "low"]].rename(
        columns={"close": "ce_close", "high": "ce_high", "low": "ce_low"})
    merged = merged.merge(
        pe0[["timestamp", "close", "high", "low"]].rename(
            columns={"close": "pe_close", "high": "pe_high", "low": "pe_low"}),
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


def _try_open(side, other, tag, prev_row, row, sl_buffer):
    """Look for a fresh close-above-UPn crossover (n=1..3) confirmed by the other
    leg sitting below ITS DNn AT THE SAME LEVEL n (e.g. UP2 entry needs the other
    leg below DN2, not DN1). Only the first level that freshly crosses this bar
    is considered (matches one signal per bar). Every entry -- at UP1 or UP2 or
    UP3 -- requires a genuine fresh crossover of that level; there is no automatic
    continuation from a previous trade."""
    for n in OFFSETS[:-1]:  # UP1..UP3 -> target UP(n+1); UP4 has no UP5 above it
        if _crossed_up(prev_row[f"{side}_close"], prev_row[f"{side}_up{n}"],
                        row[f"{side}_close"], row[f"{side}_up{n}"]):
            if row[f"{other}_close"] < row[f"{other}_dn{n}"]:
                return {
                    "time": row["timestamp"], "side": tag,
                    "line": f"{side.upper()}-UP{n}", "entry": row[f"{side}_close"],
                    "target": row[f"{side}_up{n + 1}"], "target_n": n + 1,
                    "sl": row[f"{side}_low"] - sl_buffer, "exit": None, "result": "In Trade",
                    "pnl_points": None,
                }
            return None  # crossed but not confirmed by the other leg -> no entry this bar
    return None


def _close_trade(trade, exit_price, result):
    trade["exit"] = exit_price
    trade["result"] = result
    trade["pnl_points"] = exit_price - trade["entry"]  # long-premium PnL: +ve on Target Hit, -ve on SL Hit


def build_journal(df: pd.DataFrame, max_rows: int, sl_buffer: float = 0.0,
                   no_trade_after: dtime | None = None) -> pd.DataFrame:
    """
    sl_buffer: points subtracted from the entry candle's low before it's used
        as SL, e.g. sl_buffer=2 turns a low of 75 into an SL of 73 (a little
        room below the candle so a wick-touch doesn't stop you out instantly).
    no_trade_after: no NEW entries on bars whose candle time is at/after this
        cutoff. Trades already open still get their SL/target checked and can
        still close normally.

    A Target Hit or SL Hit simply closes the trade -- there is no automatic
    continuation into the next level. A fresh entry at any level (same level
    again, or a different one) requires a brand-new close-crossover detected
    by _try_open on a later bar; price has to pull back and freshly recross.
    """
    if df.empty or len(df) < 2:
        return pd.DataFrame()

    journal = []
    open_ce = None  # dict: entry/target/target_n/sl/... or None
    open_pe = None

    prev = None
    for _, row in df.iterrows():
        if prev is not None:
            bar_time = pd.Timestamp(row["timestamp"]).time()
            entries_allowed = no_trade_after is None or bar_time < no_trade_after

            # ---- CE (bullish) side: CE breaks UPn while PE sits below PE-DN1 ----
            if open_ce is None:
                new_trade = _try_open("ce", "pe", "CE (Bullish)", prev, row, sl_buffer) if entries_allowed else None
                if new_trade:
                    open_ce = new_trade
                    journal.append(open_ce)
            else:
                if row["ce_low"] <= open_ce["sl"]:
                    _close_trade(open_ce, open_ce["sl"], "SL Hit")
                    open_ce = None
                elif not pd.isna(open_ce["target"]) and row["ce_high"] >= open_ce["target"]:
                    _close_trade(open_ce, open_ce["target"], "Target Hit")
                    open_ce = None

            # ---- PE (bearish) side: PE breaks UPn while CE sits below CE-DN1 ----
            if open_pe is None:
                new_trade = _try_open("pe", "ce", "PE (Bearish)", prev, row, sl_buffer) if entries_allowed else None
                if new_trade:
                    open_pe = new_trade
                    journal.append(open_pe)
            else:
                if row["pe_low"] <= open_pe["sl"]:
                    _close_trade(open_pe, open_pe["sl"], "SL Hit")
                    open_pe = None
                elif not pd.isna(open_pe["target"]) and row["pe_high"] >= open_pe["target"]:
                    _close_trade(open_pe, open_pe["target"], "Target Hit")
                    open_pe = None

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

    st.subheader("Signal Settings (applies to all tabs)")
    entry_tf = st.selectbox("Entry Timeframe (minutes)", [1, 3, 5, 10, 15], index=1)
    max_rows = st.number_input("Max Rows in Journal", value=20, min_value=1, max_value=200)
    sl_buffer = st.number_input(
        "SL Buffer (points below candle low)", value=2.0, min_value=0.0, step=0.5,
        help="Subtracted from the entry candle's low, e.g. low=75 with buffer=2 -> SL=73.",
    )
    no_trade_after = st.time_input("No new trades after", value=dtime(14, 45))

    st.subheader("Refresh")
    auto_refresh_on = st.checkbox(
        "Auto-refresh", value=True,
        help="Turn off after market hours to stop polling Upstox — use 'Refresh Now' in each tab instead.",
    )
    refresh_secs = st.number_input(
        "Auto-refresh (seconds)", value=30, min_value=10, max_value=300, step=5, disabled=not auto_refresh_on,
    )

st.title("Nifty / BankNifty / Sensex — CE/PE BEP Levels, Live Entry / Target / SL")

if not access_token:
    st.info("Enter your Upstox access token in the sidebar to begin.")
    st.stop()


# ======================================================================
# Per-symbol render (called inside each tab's own auto-refreshing fragment)
# ======================================================================

def render_symbol(symbol: str, tag: str, underlying_key: str, strike_step: int, expiry: date, lot_size: int):
    try:
        idx_open = fetch_nifty_open(underlying_key, access_token)
    except Exception as e:
        st.error(f"Could not fetch {symbol} open price: {e}")
        return

    atm_strike = int(round(idx_open / strike_step) * strike_step)

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

    cap_col, btn_col = st.columns([5, 1])
    with cap_col:
        refresh_desc = f"refreshing every {int(refresh_secs)}s" if auto_refresh_on else "auto-refresh OFF"
        st.caption(
            f"{symbol} open: **{idx_open:.2f}** → nearby strike **{atm_strike}** "
            f"({entry_tf}-min candles, {refresh_desc}, no new trades after {no_trade_after.strftime('%H:%M')})"
        )
    with btn_col:
        st.button("Refresh now", key=f"refresh_btn_{symbol}", use_container_width=True)

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
    journal_df = build_journal(levels_df, int(max_rows), sl_buffer=sl_buffer, no_trade_after=no_trade_after)
    st.subheader(f"Entry / Target / SL Journal (PnL @ 1 lot = {lot_size})")
    if journal_df.empty:
        st.caption("No signals yet today.")
    else:
        journal_df = journal_df.copy()
        journal_df["pnl"] = journal_df["pnl_points"] * lot_size  # keep numeric for the total below

        display_df = journal_df.rename(columns={
            "time": "Time", "side": "Side", "line": "Line",
            "entry": "Entry", "target": "Target", "sl": "SL",
            "exit": "Exit", "result": "Result", "pnl": "PnL (1 lot)",
        })
        display_df.insert(0, "Symbol", tag)  # tag every row with its own tab (NIFTY / BN / SENSEX)
        display_df["Time"] = pd.to_datetime(display_df["Time"]).dt.strftime("%H:%M")
        for c in ["Entry", "Target", "SL", "Exit"]:
            display_df[c] = display_df[c].map(lambda v: "-" if pd.isna(v) else f"{v:.2f}")
        display_df["PnL (1 lot)"] = display_df["PnL (1 lot)"].map(lambda v: "-" if pd.isna(v) else f"{v:+.2f}")
        display_df = display_df.drop(columns=["pnl_points"])

        st.dataframe(
            display_df.style.map(style_result, subset=["Result"]),
            use_container_width=True, hide_index=True,
        )

        realized = journal_df["pnl"].dropna()
        if not realized.empty:
            st.caption(
                f"Realized PnL today ({len(realized)} closed trade{'s' if len(realized) != 1 else ''}, "
                f"1 lot = {lot_size}): **{realized.sum():+.2f}**"
            )

    st.caption(f"Last updated: {pd.Timestamp.now(tz='Asia/Kolkata').strftime('%H:%M:%S')}")


# ======================================================================
# Tabs: NIFTY | BANKNIFTY | SENSEX — each with its own expiry/strike-step
# controls and its own independently auto-refreshing fragment
# ======================================================================

def _on_expiry_type_change(weekday, type_key, date_key):
    monthly = st.session_state[type_key] == "Monthly"
    st.session_state[date_key] = default_expiry(weekday, monthly)


tab_objs = st.tabs(list(TAB_CONFIGS.keys()))

for (tab_name, cfg), tab in zip(TAB_CONFIGS.items(), tab_objs):
    with tab:
        type_key = f"expiry_type_{tab_name}"
        date_key = f"expiry_{tab_name}"
        if type_key not in st.session_state:
            st.session_state[type_key] = "Monthly" if cfg["monthly_only"] else "Weekly"
        if date_key not in st.session_state:
            st.session_state[date_key] = default_expiry(cfg["expiry_weekday"], cfg["monthly_only"])

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.selectbox(
                "Expiry Type", ["Weekly", "Monthly"], key=type_key,
                on_change=_on_expiry_type_change, args=(cfg["expiry_weekday"], type_key, date_key),
                help="NIFTY/SENSEX currently trade weekly; BANKNIFTY is monthly-only since Nov 2024 "
                     "— picking a type not actually listed on the exchange will just return no contracts.",
            )
        with c2:
            tab_expiry = st.date_input("Expiry Date", key=date_key)
        with c3:
            tab_strike_step = st.number_input(
                "Strike Step", value=cfg["strike_step"], step=1, min_value=1, key=f"step_{tab_name}",
            )
        with c4:
            tab_lot_size = st.number_input(
                "Lot Size", value=cfg["lot_size"], step=1, min_value=1, key=f"lot_{tab_name}",
                help="NSE/BSE revise lot sizes periodically — update if this no longer matches the exchange.",
            )
        tab_underlying_key = st.text_input(
            "Underlying Instrument Key", value=cfg["underlying_key"], key=f"key_{tab_name}",
        )

        def _make_fragment(symbol=tab_name, tag=cfg["tag"], underlying_key=tab_underlying_key,
                            strike_step=tab_strike_step, expiry=tab_expiry, lot_size=tab_lot_size):
            run_every = f"{int(refresh_secs)}s" if auto_refresh_on else None
            @st.fragment(run_every=run_every)
            def _f():
                render_symbol(symbol, tag, underlying_key, int(strike_step), expiry, int(lot_size))
            return _f

        _make_fragment()()
