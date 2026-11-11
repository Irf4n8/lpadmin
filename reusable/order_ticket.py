#!/usr/bin/env python3
"""
Reusable Order Ticket Module
============================
Handles:
- Modal tab selection: Market, Limit, Stop HFT
- Side switching (BUY / SELL toggle)
- Dynamic field population: Lot size, Trigger price, Target (TP), Stop Loss (SL)
- Submit & auto-retry on 409 'Execution price expired'
- Order ID extraction from response payloads or toasts
"""

import re
import time
from typing import Dict, Any, Optional, Tuple
from playwright.sync_api import Frame, Page, expect


class OrderTicketModal:
    def __init__(self, frame: Frame):
        self.frame = frame

    def select_order_type(self, order_type: str = "MARKET") -> bool:
        """Selects order type tab: MARKET, LIMIT, STOP / STOP_HFT."""
        ot = order_type.upper()
        if ot == "MARKET":
            tab = self.frame.locator("#markettab, a[type='market'], [data-tab='market'], button:has-text('Market')").first
        elif ot == "LIMIT":
            tab = self.frame.locator("#limittab, a[type='limit'], [data-tab='limit'], button:has-text('Limit')").first
        elif ot in ["STOP", "STOP_HFT", "STOP_LOSS", "BRACKET"]:
            tab = self.frame.locator("#stoptab, a[type='stop'], [data-tab='stop'], button:has-text('Stop')").first
        else:
            tab = self.frame.locator("#markettab, button:has-text('Market')").first

        if tab.is_visible():
            tab.click()
            time.sleep(0.3)
            return True
        return False

    def select_side(self, side: str = "BUY") -> bool:
        """Toggles between BUY and SELL within the order modal or header."""
        side_upper = side.upper()
        if side_upper == "BUY":
            side_btn = self.frame.locator(".buy-btn, [data-side='buy'], button:has-text('Buy'), label:has-text('Buy')").first
        else:
            side_btn = self.frame.locator(".sell-btn, [data-side='sell'], button:has-text('Sell'), label:has-text('Sell')").first

        if side_btn.is_visible():
            side_btn.click()
            time.sleep(0.3)
            return True
        return False

    def fill_lot_size(self, lot: float) -> bool:
        """Fills lot / quantity input."""
        lot_input = self.frame.locator("input.lotsize, input.quantity-input, input[placeholder*='lot' i], input[placeholder*='qty' i]").first
        if lot_input.is_visible():
            lot_input.click()
            lot_input.fill(str(lot))
            return True
        return False

    def fill_trigger_price(self, trigger_price: float) -> bool:
        """Fills trigger / limit entry price."""
        trigger_input = self.frame.locator("input.trigger, input[placeholder*='trigger' i], input[placeholder*='price' i], input[name='price']").first
        if trigger_input.is_visible():
            trigger_input.click()
            trigger_input.fill(str(trigger_price))
            return True
        return False

    def fill_tp_and_sl(self, tp_price: Optional[float] = None, sl_price: Optional[float] = None) -> bool:
        """Fills Target (TP) and Stop Loss (SL) inputs."""
        if tp_price is not None:
            tp_input = self.frame.locator("input.tp, input[placeholder*='target' i], input[placeholder*='take profit' i], input[name='tp']").first
            if tp_input.is_visible():
                tp_input.click()
                tp_input.fill(str(tp_price))

        if sl_price is not None:
            sl_input = self.frame.locator("input.sl, input[placeholder*='stop loss' i], input[placeholder*='sl' i], input[name='sl']").first
            if sl_input.is_visible():
                sl_input.click()
                sl_input.fill(str(sl_price))

        return True

    def submit_and_capture_id(self, max_retries: int = 3) -> Tuple[bool, Optional[str]]:
        """
        Submits the order and captures the Order ID.
        Auto-retries on 409 'Execution price expired' up to 3 times with 800ms delay.
        """
        submit_btn = self.frame.locator(
            "button.submit-order, button:has-text('Place Order'), button:has-text('Submit'), button[type='submit'], .buy-btn, .sell-btn"
        ).first

        captured_order_id = None

        for attempt in range(1, max_retries + 1):
            if not submit_btn.is_visible():
                break

            submit_btn.click()
            time.sleep(1.0)

            # Check for toast notification or success message containing Order ID
            toasts = self.frame.locator(".toast, .alert, .notification").all_inner_texts()
            for t in toasts:
                m = re.search(r"#?(\b\d{4,}\b|ord_[a-zA-Z0-9]+)", t)
                if m:
                    captured_order_id = m.group(1)
                    return True, captured_order_id

            # Check for 409 / price expired toast
            expired = any("price expired" in t.lower() or "refresh" in t.lower() for t in toasts)
            if expired:
                print(f"[*] Requote received (attempt {attempt}/{max_retries}). Waiting 800ms for fresh tick...")
                time.sleep(0.8)
                continue

            # If modal closed or submitted successfully
            return True, captured_order_id

        return False, captured_order_id

