# Improvement delta: artifacts

Baseline is the original extraction output. Improved applies the asset rescue overwrite pass before scoring.

## Overall metrics

| Metric                            | Baseline        | Improved        | Delta  |
|-----------------------------------|-----------------|-----------------|--------|
| Dialogs with 100% correct fields  | 201/316 = 0.636 | 203/316 = 0.642 | +0.006 |
| Dialogs with >=95% correct fields | 296/316 = 0.937 | 297/316 = 0.940 | +0.003 |
| Dialogs with >=90% correct fields | 316/316 = 1.000 | 315/316 = 0.997 | -0.003 |
| Mean dialog field accuracy        | 0.988           | 0.988           | +0.000 |

## Per-entity error-rate metrics

| Entity              | Metric   | Baseline | Improved | Delta | Total cells |
|---------------------|----------|----------|----------|-------|-------------|
| households          | Missing  | 0.0%     | 0.0%     | +0.0% | 5056        |
| households          | Errors   | 0.1%     | 0.1%     | +0.0% | 5056        |
| households          | Invented | 0.0%     | 0.0%     | +0.0% | 5056        |
| people              | Missing  | 0.2%     | 0.2%     | +0.0% | 2602        |
| people              | Errors   | 0.5%     | 0.5%     | +0.0% | 2602        |
| people              | Invented | 0.0%     | 0.0%     | +0.0% | 2602        |
| income_lines        | Missing  | 0.0%     | 0.0%     | +0.0% | 2648        |
| income_lines        | Errors   | 0.1%     | 0.1%     | +0.0% | 2648        |
| income_lines        | Invented | 0.0%     | 0.0%     | +0.0% | 2648        |
| assets              | Missing  | 0.8%     | 0.8%     | +0.0% | 8635        |
| assets              | Errors   | 1.9%     | 1.8%     | -0.1% | 8635        |
| assets              | Invented | 0.0%     | 0.0%     | +0.0% | 8635        |
| liabilities         | Missing  | 0.0%     | 0.0%     | +0.0% | 1338        |
| liabilities         | Errors   | 0.0%     | 0.0%     | +0.0% | 1338        |
| liabilities         | Invented | 0.0%     | 0.0%     | +0.0% | 1338        |
| protection_policies | Missing  | 0.0%     | 0.0%     | +0.0% | 950         |
| protection_policies | Errors   | 0.0%     | 0.0%     | +0.0% | 950         |
| protection_policies | Invented | 0.0%     | 0.0%     | +0.0% | 950         |
