#!/usr/bin/env python3
"""
Reusable Helper Functions for BlackTrader Automation Framework
==============================================================
Includes:
- Dynamic symbol normalization
- Dynamic instrument precision & point multiplier calculation
- Reference base calculation for TP / SL (Market vs Pending Trigger)
- Environment and configuration loading
"""

import os
import re
from typing import Dict, Any, Optional

DEFAULT_BASE_URL = "https://lpadmin.blackfx.com"
DEFAULT_TRADER_EMAIL = "mammaster@mailinator.com"
DEFAULT_TRADER_PASSWORD = "Test@1234"


def load_env(env_path: str = ".env") -> Dict[str, str]:
    """Parse .env supporting KEY=VAL, KEY="VAL", and KEY - "VAL" formats."""
    env_vars = {}
    if not os.path.isfile(env_path):
        return env_vars
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^([A-Za-z0-9_]+)\s*[-=:]\s*(.+)$", line)
            if m:
                key, val = m.group(1).strip(), m.group(2).strip().strip("'\"")
                env_vars[key] = val
    return env_vars


def normalize_symbol(symbol: str) -> str:
    """Normalize trading symbols to BlackTrader exchange format."""
    s = symbol.strip()
    u = s.upper()

    # Dedicated Black feed crypto mapping
    if u in ["BTCUSD:BLACK", "BLACK:BTCUSD", "BTC:BLACK"]:
        return "BLACK:BTCUSD"

    # Crypto mapping
    if u in ["BTCUSD", "BTCUSDT", "BTC", "BTC/USD", "BTC/USDT", "BTCUSD BLACK"]:
        return "BINANCE:BTCUSDT.P"
    if u in ["ETHUSD", "ETHUSDT", "ETH", "ETH/USD"]:
        return "BINANCE:ETHUSDT.P"
    if u in ["SOLUSD", "SOLUSDT", "SOL"]:
        return "BINANCE:SOLUSDT.P"

    # Precious metals & commodities
    if u in ["XAGUSD:BLACK", "BLACK:XAGUSD", "XAGUSD", "SILVER", "XAG/USD"]:
        return "BLACK:XAGUSD"
    if u in ["GOLD", "XAUUSD", "XAU/USD"]:
        return "FOREX:XAUUSD"


    # Forex pairs
    if len(u) == 6 and any(cur in u for cur in ["EUR", "GBP", "USD", "JPY", "AUD", "CAD", "CHF"]):
        return f"FOREX:{u}"

    return s


def get_symbol_precision(frame_or_page: Any, symbol: str, cmp: float) -> int:
    """Dynamically infer instrument precision from modal attributes or symbol class."""
    try:
        # Check modal input attribute 'decimal' if order ticket is open
        if frame_or_page:
            input_loc = frame_or_page.locator("input.lotsize, input[data-decimal]").first
            if input_loc.count() > 0:
                dec_attr = input_loc.get_attribute("decimal") or input_loc.get_attribute("data-decimal")
                if dec_attr and dec_attr.isdigit():
                    return int(dec_attr)
    except Exception:
        pass

    # Fallback to symbol classification
    s_upper = symbol.upper()
    if "XAG" in s_upper:
        return 3
    if any(cur in s_upper for cur in ["EUR", "GBP", "AUD", "CAD", "NZD", "CHF"]):
        return 5
    if "JPY" in s_upper:
        return 3
    if "BTC" in s_upper:
        return 1 if cmp > 10000 else 2
    if cmp >= 1000:
        return 1
    if cmp >= 100:
        return 2
    if cmp >= 1.0:
        return 4
    return 6


def calculate_point_multiplier(cmp: float, precision: int = 2) -> float:
    """
    Calculate point multiplier for TP/SL and trigger calculations.
    - BTCUSD (~75,000+), XAUUSD (~4,000+): 10 pts = $10.00 (multiplier 1.0)
    - XAGUSD (~50+): 10 pts = $0.10 (multiplier 0.01)
    - EURUSD (~1.08): 10 pips = 0.0010 (multiplier 0.0001)
    """
    if cmp >= 500:
        return 1.0
    elif cmp >= 20:
        return 0.01
    elif cmp >= 1.0:
        return 0.0001
    else:
        return 10 ** (-(max(1, precision - 1)))


def calculate_order_prices(
    order_type: str,
    side: str,
    cmp: float,
    precision: int,
    trigger_offset_points: float = 0.0,
    tp_points: Optional[float] = None,
    sl_points: Optional[float] = None
) -> Dict[str, Optional[float]]:
    """
    Critical Exchange Rule: Reference Base for TP & SL
    - Market Orders: Reference base is live CMP.
        BUY:  TP = CMP + delta, SL = CMP - delta
        SELL: TP = CMP - delta, SL = CMP + delta
    - Pending Limit & Stop Orders: Reference base MUST BE THE TRIGGER (ENTRY) PRICE, NOT live CMP!
        BUY Limit / Stop:  Base = Trigger -> TP = Trigger + delta, SL = Trigger - delta
        SELL Limit / Stop: Base = Trigger -> TP = Trigger - delta, SL = Trigger + delta
    """
    mult = calculate_point_multiplier(cmp, precision)
    side_upper = side.upper()
    order_type_upper = order_type.upper()

    trigger_price = None

    if order_type_upper == "LIMIT":
        # Buy Limit: Trigger < CMP; Sell Limit: Trigger > CMP
        offset = abs(trigger_offset_points) * mult
        if side_upper == "BUY":
            trigger_price = round(cmp - offset, precision)
        else:
            trigger_price = round(cmp + offset, precision)
        base_price = trigger_price

    elif order_type_upper in ["STOP", "STOP_HFT", "STOP_LOSS", "BRACKET"]:
        # Buy Stop: Trigger > CMP; Sell Stop: Trigger < CMP
        offset = abs(trigger_offset_points) * mult
        if side_upper == "BUY":
            trigger_price = round(cmp + offset, precision)
        else:
            trigger_price = round(cmp - offset, precision)
        base_price = trigger_price

    else:
        # Market Order
        base_price = cmp

    # Calculate TP and SL relative to reference base price
    tp_price = None
    sl_price = None

    if tp_points is not None and tp_points > 0:
        tp_delta = tp_points * mult
        if side_upper == "BUY":
            tp_price = round(base_price + tp_delta, precision)
        else:
            tp_price = round(base_price - tp_delta, precision)

    if sl_points is not None and sl_points > 0:
        sl_delta = sl_points * mult
        if side_upper == "BUY":
            sl_price = round(base_price - sl_delta, precision)
        else:
            sl_price = round(base_price + sl_delta, precision)

    return {
        "cmp": cmp,
        "base_price": base_price,
        "trigger_price": trigger_price,
        "tp_price": tp_price,
        "sl_price": sl_price,
        "precision": precision,
        "point_multiplier": mult
    }

