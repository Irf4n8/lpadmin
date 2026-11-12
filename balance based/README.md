# Balance Based MAM Category Test Suite

This folder contains test cases specifically designed to validate MAM order replication under the **Balance Based** allocation category.

## Sizing Formula
$$\text{Follower Lot} = \text{Master Lot} \times \left( \frac{\text{Follower Balance}}{\text{Master Balance}} \right)$$

## Switching Category to Balance Based
Before running tests in this folder, ensure followers are configured in Balance Based mode using the unified category manager:

```powershell
python mam_management/change_mam_category.py --category balance
```

## Running Tests
```powershell
python "balance based/run_balance_test_cases.py"
```

