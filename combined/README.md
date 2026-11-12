# Combined / Hybrid MAM Test Suite

This folder contains test cases for testing hybrid follower allocations across the fleet simultaneously:
- **Cohort 1** (Followers 1–33): Multiplier Mode (2.0x)
- **Cohort 2** (Followers 34–66): Equity Based Mode
- **Cohort 3** (Followers 67–100): Balance Based Mode

## Setting Up Fleet Cohorts
```powershell
# Cohort 1 -> Multiplier
python mam_management/change_mam_category.py --start 1 --end 33 --category multiplier --multiplier 2.0

# Cohort 2 -> Equity Based
python mam_management/change_mam_category.py --start 34 --end 66 --category equity

# Cohort 3 -> Balance Based
python mam_management/change_mam_category.py --start 67 --end 100 --category balance
```

## Running Tests
```powershell
python "combined/run_combined_test_cases.py"
```

