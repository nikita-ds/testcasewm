# Extraction discrepancy analysis

## Overall

- Households analyzed: **99**
- Scored cells: **6607**
- Match rate (cells): **0.987**

### Error breakdown (scored cells)

- Missing extracted: **33**
- Extra extracted: **0**
- Value mismatch: **50**

## Record pairing by entity

| entity | record_pairs | records_both_present | records_gt_only | records_ex_only | both_present_rate | sample_gt_only_keys | sample_ex_only_keys |
| --- | --- | --- | --- | --- | --- | --- | --- |
| income_lines | 280 | 224 | 1 | 55 | 0.8 | HH000827_I5 | HH000147_I1,HH000147_I2,HH000182_I1,HH000182_I2,HH000286_I1 |
| liabilities | 78 | 69 | 0 | 9 | 0.884615 |  | HH003198_L1,HH003218_L1,HH003218_L2,HH003218_L3,HH003522_L1 |
| protection_policies | 56 | 54 | 0 | 2 | 0.964286 |  | P1,P2 |
| assets | 496 | 488 | 0 | 8 | 0.983871 |  | HH000340_A3,HH000340_A7,HH000659_A6,4,HH002286_A5 |
| people | 174 | 174 | 0 | 0 | 1 |  |  |
| households | 99 | 99 | 0 | 0 | 1 |  |  |

## Worst fields (by match rate)

| entity | field | field_type | n_total | match_rate | n_missing_extracted | n_extra_extracted | n_value_mismatch |
| --- | --- | --- | --- | --- | --- | --- | --- |
| assets | provider_type | categorical | 273 | 0.959707 | 9 | 0 | 2 |
| assets | owner | categorical | 488 | 0.961066 | 10 | 0 | 9 |
| assets | is_joint | boolean | 488 | 0.965164 | 10 | 0 | 7 |
| assets | asset_type | categorical | 488 | 0.971311 | 0 | 0 | 14 |
| assets | subtype | categorical | 488 | 0.971311 | 0 | 0 | 14 |
| people | occupation_group | categorical | 103 | 0.980583 | 0 | 0 | 2 |
| households | annual_household_gross_income | continuous | 99 | 0.989899 | 0 | 0 | 1 |
| income_lines | amount_annualized | continuous | 225 | 0.991111 | 1 | 0 | 1 |
| income_lines | frequency | categorical | 225 | 0.995556 | 1 | 0 | 0 |
| income_lines | owner | categorical | 225 | 0.995556 | 1 | 0 | 0 |
| income_lines | source_type | categorical | 225 | 0.995556 | 1 | 0 | 0 |
| assets | value | continuous | 488 | 1 | 0 | 0 | 0 |
| people | client_no | integer | 174 | 1 | 0 | 0 | 0 |
| people | employment_status | categorical | 174 | 1 | 0 | 0 | 0 |
| people | gross_annual_income | continuous | 174 | 1 | 0 | 0 | 0 |
| people | role | categorical | 174 | 1 | 0 | 0 | 0 |
| households | country | categorical | 99 | 1 | 0 | 0 | 0 |
| households | investable_assets_total | continuous | 99 | 1 | 0 | 0 | 0 |
| households | loan_outstanding_total | continuous | 99 | 1 | 0 | 0 | 0 |
| households | marital_status | categorical | 99 | 1 | 0 | 0 | 0 |
| households | market | categorical | 99 | 1 | 0 | 0 | 0 |
| households | monthly_debt_cost_total | continuous | 99 | 1 | 0 | 0 | 0 |
| households | monthly_expenses_total | continuous | 99 | 1 | 0 | 0 | 0 |
| households | mortgage_outstanding_total | continuous | 99 | 1 | 0 | 0 | 0 |
| households | non_mortgage_outstanding_total | continuous | 99 | 1 | 0 | 0 | 0 |

## Missing extracted: why?

Missing extracted happens for two different reasons: (a) **record pairing failed** (GT record exists but no extracted record matched its primary key), and (b) **within a paired record**, extracted left a specific field empty.

### Top missing due to unpaired records (gt_only)

| entity | field | field_type | n_total | n_missing_extracted_gt_only | n_missing_extracted |
| --- | --- | --- | --- | --- | --- |
| income_lines | amount_annualized | continuous | 225 | 1 | 1 |
| income_lines | frequency | categorical | 225 | 1 | 1 |
| income_lines | owner | categorical | 225 | 1 | 1 |
| income_lines | source_type | categorical | 225 | 1 | 1 |
| assets | owner | categorical | 488 | 0 | 10 |
| assets | is_joint | boolean | 488 | 0 | 10 |
| assets | provider_type | categorical | 273 | 0 | 9 |
| assets | asset_type | categorical | 488 | 0 | 0 |
| assets | subtype | categorical | 488 | 0 | 0 |
| people | occupation_group | categorical | 103 | 0 | 0 |
| households | annual_household_gross_income | continuous | 99 | 0 | 0 |
| assets | value | continuous | 488 | 0 | 0 |
| people | client_no | integer | 174 | 0 | 0 |
| people | employment_status | categorical | 174 | 0 | 0 |
| people | gross_annual_income | continuous | 174 | 0 | 0 |
| people | role | categorical | 174 | 0 | 0 |
| households | country | categorical | 99 | 0 | 0 |
| households | investable_assets_total | continuous | 99 | 0 | 0 |
| households | loan_outstanding_total | continuous | 99 | 0 | 0 |
| households | marital_status | categorical | 99 | 0 | 0 |

### Top missing within paired records (both)

| entity | field | field_type | n_total | n_missing_extracted_within_paired | n_missing_extracted |
| --- | --- | --- | --- | --- | --- |
| assets | owner | categorical | 488 | 10 | 10 |
| assets | is_joint | boolean | 488 | 10 | 10 |
| assets | provider_type | categorical | 273 | 9 | 9 |
| income_lines | amount_annualized | continuous | 225 | 0 | 1 |
| income_lines | frequency | categorical | 225 | 0 | 1 |
| income_lines | owner | categorical | 225 | 0 | 1 |
| income_lines | source_type | categorical | 225 | 0 | 1 |
| assets | asset_type | categorical | 488 | 0 | 0 |
| assets | subtype | categorical | 488 | 0 | 0 |
| people | occupation_group | categorical | 103 | 0 | 0 |
| households | annual_household_gross_income | continuous | 99 | 0 | 0 |
| assets | value | continuous | 488 | 0 | 0 |
| people | client_no | integer | 174 | 0 | 0 |
| people | employment_status | categorical | 174 | 0 | 0 |
| people | gross_annual_income | continuous | 174 | 0 | 0 |
| people | role | categorical | 174 | 0 | 0 |
| households | country | categorical | 99 | 0 | 0 |
| households | investable_assets_total | continuous | 99 | 0 | 0 |
| households | loan_outstanding_total | continuous | 99 | 0 | 0 |
| households | marital_status | categorical | 99 | 0 | 0 |

## Common mismatch examples

| entity | field | ground_truth | extracted | count |
| --- | --- | --- | --- | --- |
| assets | is_joint | False | True | 6 |
| assets | owner | client_1 | joint | 4 |
| assets | subtype | bank_account | 401k_ira | 4 |
| assets | asset_type | cash | retirement | 4 |
| assets | subtype | bank_account | taxable_brokerage | 3 |
| assets | asset_type | cash | brokerage | 3 |
| assets | subtype | taxable_brokerage | bank_account | 2 |
| assets | asset_type | brokerage | alternatives | 2 |
| assets | owner | joint | client_1 | 2 |
| assets | owner | client_2 | joint | 2 |
| assets | subtype | taxable_brokerage | private_markets | 2 |
| assets | asset_type | brokerage | cash | 2 |
| assets | subtype | private_markets | bank_account | 1 |
| households | annual_household_gross_income | 116750 | 233500 | 1 |
| income_lines | amount_annualized | 145100 | 92100 | 1 |
| people | occupation_group | education | business_owner | 1 |
| assets | subtype | taxable_brokerage | 401k_ira | 1 |
| assets | asset_type | alternatives | cash | 1 |
| assets | provider_type | brokerage | bank | 1 |
| assets | subtype | 401k_ira | bank_account | 1 |
| assets | provider_type | insurance_company | bank | 1 |
| assets | owner | client_1 | client_2 | 1 |
| assets | is_joint | True | False | 1 |
| assets | asset_type | retirement | cash | 1 |
| assets | asset_type | brokerage | retirement | 1 |
| people | occupation_group | exec | operations | 1 |

