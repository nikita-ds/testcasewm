# Extraction discrepancy analysis

## Overall

- Households analyzed: **316**
- Scored cells: **21229**
- Match rate (cells): **0.988**

### Error breakdown (scored cells)

- Missing extracted: **73**
- Extra extracted: **0**
- Value mismatch: **184**

## Record pairing by entity

| entity | record_pairs | records_both_present | records_gt_only | records_ex_only | both_present_rate | sample_gt_only_keys | sample_ex_only_keys |
| --- | --- | --- | --- | --- | --- | --- | --- |
| income_lines | 844 | 662 | 0 | 182 | 0.78436 |  | HH000018_I1,HH000018_I2,HH000059_I1,HH000059_I2,HH000174_I1 |
| liabilities | 305 | 272 | 0 | 33 | 0.891803 |  | HH000018_L1,HH000018_L2,HH000018_L3,HH000226_L1,HH000226_L2 |
| protection_policies | 196 | 190 | 0 | 6 | 0.969388 |  | POLICY_HH000174_1,POLICY_HH000174_2,P1,P2,P3 |
| assets | 1564 | 1557 | 0 | 7 | 0.995524 |  | HH001908_A5,HH002044_A6,HH002171_A5,HH002321_A3,HH003034_A4 |
| people | 564 | 564 | 0 | 0 | 1 |  |  |
| households | 316 | 316 | 0 | 0 | 1 |  |  |

## Worst fields (by match rate)

| entity | field | field_type | n_total | match_rate | n_missing_extracted | n_extra_extracted | n_value_mismatch |
| --- | --- | --- | --- | --- | --- | --- | --- |
| assets | provider_type | categorical | 850 | 0.954118 | 19 | 0 | 20 |
| assets | is_joint | boolean | 1557 | 0.959538 | 24 | 0 | 39 |
| assets | owner | categorical | 1557 | 0.96018 | 24 | 0 | 38 |
| people | occupation_group | categorical | 346 | 0.965318 | 2 | 0 | 10 |
| assets | asset_type | categorical | 1557 | 0.975594 | 0 | 0 | 38 |
| assets | subtype | categorical | 1557 | 0.978805 | 1 | 0 | 32 |
| people | gross_annual_income | continuous | 564 | 0.994681 | 3 | 0 | 0 |
| people | employment_status | categorical | 564 | 0.996454 | 0 | 0 | 2 |
| households | annual_household_gross_income | continuous | 316 | 0.996835 | 0 | 0 | 1 |
| households | monthly_expenses_total | continuous | 316 | 0.996835 | 0 | 0 | 1 |
| households | risk_tolerance | categorical | 316 | 0.996835 | 0 | 0 | 1 |
| income_lines | amount_annualized | continuous | 662 | 0.998489 | 0 | 0 | 1 |
| income_lines | frequency | categorical | 662 | 0.998489 | 0 | 0 | 1 |
| assets | value | continuous | 1557 | 1 | 0 | 0 | 0 |
| income_lines | owner | categorical | 662 | 1 | 0 | 0 | 0 |
| income_lines | source_type | categorical | 662 | 1 | 0 | 0 | 0 |
| people | client_no | integer | 564 | 1 | 0 | 0 | 0 |
| people | role | categorical | 564 | 1 | 0 | 0 | 0 |
| households | country | categorical | 316 | 1 | 0 | 0 | 0 |
| households | investable_assets_total | continuous | 316 | 1 | 0 | 0 | 0 |
| households | loan_outstanding_total | continuous | 316 | 1 | 0 | 0 | 0 |
| households | marital_status | categorical | 316 | 1 | 0 | 0 | 0 |
| households | market | categorical | 316 | 1 | 0 | 0 | 0 |
| households | monthly_debt_cost_total | continuous | 316 | 1 | 0 | 0 | 0 |
| households | mortgage_outstanding_total | continuous | 316 | 1 | 0 | 0 | 0 |

## Missing extracted: why?

Missing extracted happens for two different reasons: (a) **record pairing failed** (GT record exists but no extracted record matched its primary key), and (b) **within a paired record**, extracted left a specific field empty.

### Top missing due to unpaired records (gt_only)

| entity | field | field_type | n_total | n_missing_extracted_gt_only | n_missing_extracted |
| --- | --- | --- | --- | --- | --- |
| assets | is_joint | boolean | 1557 | 0 | 24 |
| assets | owner | categorical | 1557 | 0 | 24 |
| assets | provider_type | categorical | 850 | 0 | 19 |
| people | gross_annual_income | continuous | 564 | 0 | 3 |
| people | occupation_group | categorical | 346 | 0 | 2 |
| assets | subtype | categorical | 1557 | 0 | 1 |
| assets | asset_type | categorical | 1557 | 0 | 0 |
| people | employment_status | categorical | 564 | 0 | 0 |
| households | annual_household_gross_income | continuous | 316 | 0 | 0 |
| households | monthly_expenses_total | continuous | 316 | 0 | 0 |
| households | risk_tolerance | categorical | 316 | 0 | 0 |
| income_lines | amount_annualized | continuous | 662 | 0 | 0 |
| income_lines | frequency | categorical | 662 | 0 | 0 |
| assets | value | continuous | 1557 | 0 | 0 |
| income_lines | owner | categorical | 662 | 0 | 0 |
| income_lines | source_type | categorical | 662 | 0 | 0 |
| people | client_no | integer | 564 | 0 | 0 |
| people | role | categorical | 564 | 0 | 0 |
| households | country | categorical | 316 | 0 | 0 |
| households | investable_assets_total | continuous | 316 | 0 | 0 |

### Top missing within paired records (both)

| entity | field | field_type | n_total | n_missing_extracted_within_paired | n_missing_extracted |
| --- | --- | --- | --- | --- | --- |
| assets | is_joint | boolean | 1557 | 24 | 24 |
| assets | owner | categorical | 1557 | 24 | 24 |
| assets | provider_type | categorical | 850 | 19 | 19 |
| people | gross_annual_income | continuous | 564 | 3 | 3 |
| people | occupation_group | categorical | 346 | 2 | 2 |
| assets | subtype | categorical | 1557 | 1 | 1 |
| assets | asset_type | categorical | 1557 | 0 | 0 |
| people | employment_status | categorical | 564 | 0 | 0 |
| households | annual_household_gross_income | continuous | 316 | 0 | 0 |
| households | monthly_expenses_total | continuous | 316 | 0 | 0 |
| households | risk_tolerance | categorical | 316 | 0 | 0 |
| income_lines | amount_annualized | continuous | 662 | 0 | 0 |
| income_lines | frequency | categorical | 662 | 0 | 0 |
| assets | value | continuous | 1557 | 0 | 0 |
| income_lines | owner | categorical | 662 | 0 | 0 |
| income_lines | source_type | categorical | 662 | 0 | 0 |
| people | client_no | integer | 564 | 0 | 0 |
| people | role | categorical | 564 | 0 | 0 |
| households | country | categorical | 316 | 0 | 0 |
| households | investable_assets_total | continuous | 316 | 0 | 0 |

## Common mismatch examples

| entity | field | ground_truth | extracted | count |
| --- | --- | --- | --- | --- |
| assets | is_joint | False | True | 37 |
| assets | owner | client_1 | joint | 26 |
| assets | asset_type | cash | retirement | 13 |
| assets | subtype | bank_account | 401k_ira | 10 |
| assets | asset_type | brokerage | cash | 9 |
| assets | subtype | taxable_brokerage | bank_account | 9 |
| assets | owner | client_2 | joint | 6 |
| assets | asset_type | retirement | cash | 5 |
| assets | subtype | 401k_ira | bank_account | 5 |
| assets | provider_type | brokerage | advisor_platform | 4 |
| assets | asset_type | cash | brokerage | 4 |
| assets | asset_type | cash | alternatives | 3 |
| assets | subtype | bank_account | taxable_brokerage | 3 |
| assets | provider_type | bank | brokerage | 3 |
| assets | owner | joint | client_1 | 3 |
| assets | provider_type | retirement_platform | advisor_platform | 2 |
| assets | asset_type | brokerage | alternatives | 2 |
| assets | provider_type | insurance_company | bank | 2 |
| people | employment_status | employed | employed_full_time | 2 |
| assets | subtype | bank_account | private_markets | 2 |
| assets | provider_type | retirement_platform | bank | 2 |
| assets | provider_type | bank | advisor_platform | 2 |
| assets | owner | client_2 | client_1 | 2 |
| assets | is_joint | True | False | 2 |
| assets | provider_type | brokerage | bank | 2 |
| assets | provider_type | insurance_company | advisor_platform | 1 |
| income_lines | frequency | annual | monthly | 1 |
| people | occupation_group | professional | business_owner | 1 |
| people | occupation_group | operations | business_owner | 1 |
| people | occupation_group | healthcare | operations | 1 |
| people | occupation_group | healthcare | finance | 1 |
| people | occupation_group | finance | professional | 1 |
| people | occupation_group | finance | inactive | 1 |
| people | occupation_group | exec | business_owner | 1 |
| people | occupation_group | business_owner | operations | 1 |
| people | occupation_group | business_owner | education | 1 |
| assets | asset_type | brokerage | retirement | 1 |
| households | risk_tolerance | aggressive | conservative | 1 |
| income_lines | amount_annualized | 154650 | 55350 | 1 |
| households | monthly_expenses_total | 6000 | 6700 | 1 |

