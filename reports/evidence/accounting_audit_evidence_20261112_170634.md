# Accounting Reconciliation & Aggregate PnL Audit Evidence Report

**Generated:** 2026-11-12T11:36:34.509731+00:00  
**Master Trader:** `ctmaster@mailinator.com`  
**Followers Tested:** 100 (`follower1@mailinator.com` to `follower100@mailinator.com`)  
**Overall Result:** **✅ PASS**

---

## 1. Mathematical PnL Reconciliation

$$\sum_{i=1}^{100} \text{Follower PnL}_i = \text{Master PnL} \times 162.5\times$$

| Accounting Metric | Value |
| :--- | :--- |
| **Master Trade PnL** | `+0.1900 USD` |
| **Total Followers PnL (Actual)** | `+30.8750 USD` |
| **Total Followers PnL (Theoretical)** | `+30.8750 USD` |
| **Effective Multiplier Ratio** | **`162.50x`** (Target: `162.50x`) |
| **Mathematical Reconciliation** | ✅ PASS |

---

## 2. Cohort PnL Distribution

| Cohort | Multiplier | Followers | Actual PnL Sum | Expected PnL Sum | Result |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Tier 1 (F1–F25)** | 1.0x | 25 | `+4.7500 USD` | `+4.7500 USD` | ✅ PASS |
| **Tier 2 (F26–F50)** | 2.0x | 25 | `+9.5000 USD` | `+9.5000 USD` | ✅ PASS |
| **Tier 3 (F51–F75)** | 3.0x | 25 | `+14.2500 USD` | `+14.2500 USD` | ✅ PASS |
| **Tier 4 (F76–F100)** | 0.5x | 25 | `+2.3750 USD` | `+2.3750 USD` | ✅ PASS |

---

## 3. Balance & Margin Integrity
- **Zero Stuck Margin:** Confirmed `used_margin == 0.00` across all 101 accounts after position close.
- **Equity Cleanliness:** Confirmed `ending_equity == ending_balance` with zero un-reconciled floating PnL.
