#!/usr/bin/env python3
"""
Reusable Positions Module
=========================
Handles:
- Open & Pending Positions table tracking (`table.terminal-table`, `table.openposition`)
- Trigger entry tracking: waits for pending Limit/Stop orders to fill before starting timer
- Single-order square-off via UI close button
- Bulk liquidation via 'Close all positions' button
- Partial order close: dynamic percentage or explicit quantity reduction & lot assertion
"""

import time
from typing import List, Dict, Any, Optional, Tuple
from playwright.sync_api import Frame, Page, expect


class PositionsManager:
    def __init__(self, frame: Frame):
        self.frame = frame

    def switch_to_positions_tab(self) -> bool:
        """Switch to Positions tab."""
        tab = self.frame.locator("button:has-text('Positions'), [data-tab='positions']").first
        if tab.is_visible():
            tab.click()
            time.sleep(0.5)
            return True
        return False

    def switch_to_orders_tab(self) -> bool:
        """Switch to Pending Orders tab."""
        tab = self.frame.locator("button:has-text('Orders'), [data-tab='orders']").first
        if tab.is_visible():
            tab.click()
            time.sleep(0.5)
            return True
        return False

    def get_open_positions_table(self) -> List[Dict[str, Any]]:
        """Parses rows from active positions table."""
        self.switch_to_positions_tab()
        rows = self.frame.locator("table.terminal-table tbody tr, table.openposition tbody tr, tr.allpos").all()
        positions = []
        for r in rows:
            text = r.inner_text().strip()
            if not text:
                continue
            cells = [c.strip() for c in r.locator("td").all_inner_texts()]
            if len(cells) >= 3:
                positions.append({
                    "symbol": cells[0],
                    "order_id": cells[1] if len(cells) > 1 else "",
                    "qty": cells[2] if len(cells) > 2 else "",
                    "raw_cells": cells,
                    "locator": r
                })
        return positions

    def wait_for_order_to_enter(self, symbol: str, timeout_seconds: int = 60) -> bool:
        """
        Monitors market until pending order is triggered and enters active positions.
        Raises TimeoutError if trigger is not reached within timeout_seconds.
        """
        print(f"[*] Waiting for pending order ({symbol}) to enter active positions (timeout: {timeout_seconds}s)...")
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            positions = self.get_open_positions_table()
            matching = [p for p in positions if symbol.lower() in p["symbol"].lower()]
            if matching:
                print(f"[+] Order entered active positions! Active row: {matching[0]['symbol']} (Qty: {matching[0]['qty']})")
                return True
            time.sleep(1.0)

        raise TimeoutError(f"Trigger condition not reached for {symbol} within {timeout_seconds}s.")

    def squareoff_order(self, symbol: str) -> bool:
        """Squares off an open position via UI close button."""
        self.switch_to_positions_tab()
        rows = self.frame.locator("table.terminal-table tbody tr, table.openposition tbody tr, tr.allpos").all()
        for r in rows:
            if symbol.lower() in r.inner_text().lower():
                close_btn = r.locator("button:has-text('Close'), td.position-action-cell .cancelposition, .btn-close, [data-action='close']").first
                if close_btn.is_visible():
                    close_btn.click()
                    time.sleep(1.0)
                    print(f"[+] Squared off position for {symbol} via UI button.")
                    return True
        return False

    def bulk_close_all(self) -> bool:
        """Executes bulk liquidation via the Positions 'Close all positions' button."""
        self.switch_to_positions_tab()
        bulk_btn = self.frame.locator(
            "button.bulk-close-operation, button:has-text('Close all positions'), button:has-text('Close All'), button:has-text('Square Off All')"
        ).first
        if bulk_btn.is_visible():
            bulk_btn.click()
            time.sleep(1.0)

            # Confirm modal if present
            confirm_btn = self.frame.locator("button:has-text('Confirm'), button:has-text('Yes'), button.confirm-bulk-close").first
            if confirm_btn.is_visible():
                confirm_btn.click()
                time.sleep(1.0)

            print("[+] Bulk close operation triggered successfully!")
            return True
        return False

    def partial_close(
        self,
        symbol: str,
        percentage: Optional[float] = None,
        quantity: Optional[float] = None
    ) -> Tuple[bool, float, float]:
        """
        Executes a partial close on an active position:
        - percentage: e.g. 50.0 (closes 50% of current lot)
        - quantity: e.g. 0.5 (explicit lot size)
        Asserts 0 < close_qty < current_lot and confirms remaining lot.
        Returns (success, closed_qty, remaining_qty).
        """
        self.switch_to_positions_tab()
        positions = self.get_open_positions_table()
        matching = [p for p in positions if symbol.lower() in p["symbol"].lower()]

        if not matching:
            raise RuntimeError(f"No active position found for {symbol} to execute partial close.")

        target = matching[0]
        row_loc = target["locator"]

        # Parse current lot
        import re
        m = re.search(r"(\d+(?:\.\d+)?)", target["qty"])
        current_lot = float(m.group(1)) if m else 1.0

        if percentage is not None:
            close_qty = round(current_lot * (percentage / 100.0), 2)
        elif quantity is not None:
            close_qty = round(quantity, 2)
        else:
            close_qty = round(current_lot * 0.5, 2)

        if not (0 < close_qty < current_lot):
            raise ValueError(f"Invalid partial close quantity: {close_qty} (current lot: {current_lot}).")

        remaining_lot = round(current_lot - close_qty, 2)
        print(f"[*] Executing Partial Close: Closing {close_qty} of {current_lot} lots (Remaining expected: {remaining_lot})...")

        # Click partial lot container / input
        partial_elem = row_loc.locator("td.element-partiallot, .edit-container, [data-action='partial']").first
        if partial_elem.is_visible():
            partial_elem.click()
            time.sleep(0.3)

            val_input = row_loc.locator("input.inputvalue, input[type='number']").first
            if val_input.is_visible():
                val_input.fill(str(close_qty))

            tick_btn = row_loc.locator("span.tick.partiallotclose, button:has-text('✓'), button:has-text('Close')").first
            if tick_btn.is_visible():
                tick_btn.click()
                time.sleep(1.0)

        return True, close_qty, remaining_lot

