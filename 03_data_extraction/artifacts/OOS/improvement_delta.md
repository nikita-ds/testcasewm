# Improvement delta: OOS

Baseline is the original extraction output. Improved applies the asset rescue overwrite pass before scoring.

## Overall metrics

| Metric                            | Baseline      | Improved      | Delta  |
|-----------------------------------|---------------|---------------|--------|
| Dialogs with 100% correct fields  | 58/99 = 0.586 | 59/99 = 0.596 | +0.010 |
| Dialogs with >=95% correct fields | 95/99 = 0.960 | 96/99 = 0.970 | +0.010 |
| Dialogs with >=90% correct fields | 99/99 = 1.000 | 99/99 = 1.000 | +0.000 |
| Mean dialog field accuracy        | 0.987         | 0.988         | +0.001 |

## Per-entity error-rate metrics

| Entity              | Metric   | Baseline | Improved | Delta | Total cells |
|---------------------|----------|----------|----------|-------|-------------|
| households          | Missing  | 0.0%     | 0.0%     | +0.0% | 1584        |
| households          | Errors   | 0.1%     | 0.1%     | +0.0% | 1584        |
| households          | Invented | 0.0%     | 0.0%     | +0.0% | 1584        |
| people              | Missing  | 0.0%     | 0.0%     | +0.0% | 799         |
| people              | Errors   | 0.3%     | 0.3%     | +0.0% | 799         |
| people              | Invented | 0.0%     | 0.0%     | +0.0% | 799         |
| income_lines        | Missing  | 0.4%     | 0.4%     | +0.0% | 900         |
| income_lines        | Errors   | 0.1%     | 0.1%     | +0.0% | 900         |
| income_lines        | Invented | 0.0%     | 0.0%     | +0.0% | 900         |
| assets              | Missing  | 1.1%     | 1.1%     | +0.0% | 2713        |
| assets              | Errors   | 1.7%     | 1.5%     | -0.2% | 2713        |
| assets              | Invented | 0.0%     | 0.0%     | +0.0% | 2713        |
| liabilities         | Missing  | 0.0%     | 0.0%     | +0.0% | 341         |
| liabilities         | Errors   | 0.0%     | 0.0%     | +0.0% | 341         |
| liabilities         | Invented | 0.0%     | 0.0%     | +0.0% | 341         |
| protection_policies | Missing  | 0.0%     | 0.0%     | +0.0% | 270         |
| protection_policies | Errors   | 0.0%     | 0.0%     | +0.0% | 270         |
| protection_policies | Invented | 0.0%     | 0.0%     | +0.0% | 270         |
