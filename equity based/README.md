# Equity Based MAM Category Test Suite

This folder contains test cases specifically designed to validate MAM order replication under the **Equity Based** allocation category.

## Sizing Formula
$$\text{Follower Lot} = \text{Master Lot} \times \left( \frac{\text{Follower Equity}}{\text{Master Balance}} \right)$$

## Switching Category to Equity Based
Before running tests in this folder, ensure followers are configured in Equity Based mode using the unified category manager:

```powershell
python mam_management/change_mam_category.py --category equity
```

## Running Tests
```powershell
python "equity based/run_equity_test_cases.py"
```

