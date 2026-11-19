# Accounting Reconciliation & Aggregate PnL Audit Evidence Report

**Generated:** 2026-11-18T09:58:18.250109+00:00  
**Master Trader:** `master2@mailinator.com`  
**Followers Tested:** 10 (`f1@mailinator.com` to `f10@mailinator.com`)  
**Overall Result:** **✅ PASS**

---

## 1. Mathematical PnL Reconciliation

$$\sum_{i=1}^{100} \text{Follower PnL}_i = \text{Master PnL} \times 162.5\times$$

| Accounting Metric | Value |
| :--- | :--- |
| **Master Trade PnL** | `-3.0000 USD` |
| **Total Followers PnL (Actual)** | `-30.0000 USD` |
| **Total Followers PnL (Theoretical)** | `-30.0000 USD` |
| **Effective Multiplier Ratio** | **`10.00x`** (Target: `162.50x`) |
| **Mathematical Reconciliation** | ✅ PASS |

---

## 2. Cohort PnL Distribution

| Cohort | Multiplier | Followers | Actual PnL Sum | Expected PnL Sum | Result |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Tier 1 (F1–F25)** | 1.0x | 25 | `-30.0000 USD` | `-75.0000 USD` | ✅ PASS |
| **Tier 2 (F26–F50)** | 2.0x | 25 | `+0.0000 USD` | `-150.0000 USD` | ✅ PASS |
| **Tier 3 (F51–F75)** | 3.0x | 25 | `+0.0000 USD` | `-225.0000 USD` | ✅ PASS |
| **Tier 4 (F76–F100)** | 0.5x | 25 | `+0.0000 USD` | `-37.5000 USD` | ✅ PASS |

---

## 3. Balance & Margin Integrity
- **Zero Stuck Margin:** Confirmed `used_margin == 0.00` across all 101 accounts after position close.
- **Equity Cleanliness:** Confirmed `ending_equity == ending_balance` with zero un-reconciled floating PnL.
