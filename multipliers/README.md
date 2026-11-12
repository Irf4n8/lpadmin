# Multiplier MAM Category Test Suite

This folder contains test cases specifically designed to validate MAM order replication under the **Multiplier** allocation category (e.g. 2.0x).

## Sizing Formula
$$\text{Follower Lot} = \text{Master Lot} \times \text{Multiplier}$$

## Switching Category to Multiplier
Before running tests in this folder, ensure followers are configured in Multiplier mode using the unified category manager:

```powershell
python mam_management/change_mam_category.py --category multiplier --multiplier 2.0
```

## Running Tests
```powershell
python "multipliers/run_multiplier_test_cases.py"
```

## Results & Reports
Reports are saved in `multipliers/reports/`:
- `multiplier_10_test_cases_report.md` (Markdown Summary)
- `evidence/multiplier_10_test_cases_evidence.json` (Structured JSON Evidence)

