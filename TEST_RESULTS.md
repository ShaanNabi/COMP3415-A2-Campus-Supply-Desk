# Test Results

Run all tests from the repository root:

```sh
python -m unittest discover -s tests -v
```

| Stage | Tests run | Passed | Failed |
|---|---|---|---|
| Baseline (starter tests + safety net, before refactoring) | 25 | 22 | 3 |
| After refactoring 1 (magic numbers) | 25 | 22 | 3 |
| After refactoring 2 (duplicated code) | 25 | 22 | 3 |
| After refactoring 3 (long method) | 25 | 22 | 3 |
| CR-01 tests added, before implementation | 36 | 24 | 12 (9 new CR-01 tests + the 3 known defects) |
| After CR-01 (express delivery) | 36 | 33 | 3 (the 3 known defects) |

The same 3 tests fail at every stage. They are known defects found in Task 2 and were
not fixed because refactoring and CR-01 should not change existing behaviour:

- `test_student_discount_applies_at_exactly_5000` (discount uses `>` instead of at least $50)
- `test_duplicate_lines_cannot_exceed_combined_stock` (stock is checked per line, not per product)
- `test_cancelling_twice_does_not_restore_stock_again` (a second cancel restores stock again)

All 11 tests in `tests/test_cr01_express.py` pass after CR-01.
