# Extraction discrepancy analysis

## Overall

- Households analyzed: **316**
- Scored cells: **18815**
- Match rate (cells): **0.991**

### Error breakdown (scored cells)

- Missing extracted: **31**
- Extra extracted: **0**
- Value mismatch: **129**

## Record pairing by entity

| entity | record_pairs | records_both_present | records_gt_only | records_ex_only | both_present_rate | sample_gt_only_keys | sample_ex_only_keys |
| --- | --- | --- | --- | --- | --- | --- | --- |
| income_lines | 849 | 662 | 0 | 187 | 0.779741 |  | HH000018_I1,HH000018_I2,HH000059_I1,HH000059_I2,inc_4 |
| liabilities | 317 | 272 | 0 | 45 | 0.858044 |  | HH000018_L1,HH000018_L2,HH000018_L3,HH000226_L1,HH000226_L2 |
| protection_policies | 199 | 190 | 0 | 9 | 0.954774 |  | P1,P2,P3,POL_HH003182_1,POL_HH003182_2 |
| assets | 1566 | 1557 | 0 | 9 | 0.994253 |  | HH001292_A6,HH001435_A4,HH001908_A6,HH002171_A5,HH002537_A2 |
| people | 564 | 564 | 0 | 0 | 1 |  |  |
| households | 316 | 316 | 0 | 0 | 1 |  |  |

## Worst fields (by match rate)

| entity | field | field_type | n_total | match_rate | n_missing_extracted | n_extra_extracted | n_value_mismatch |
| --- | --- | --- | --- | --- | --- | --- | --- |
| people | occupation_group | categorical | 328 | 0.926829 | 4 | 0 | 20 |
| assets | provider_type | categorical | 850 | 0.958824 | 18 | 0 | 17 |
| assets | owner | categorical | 359 | 0.963788 | 0 | 0 | 13 |
| assets | is_joint | boolean | 359 | 0.969359 | 0 | 0 | 11 |
| assets | asset_type | categorical | 1557 | 0.978163 | 0 | 0 | 34 |
| assets | subtype | categorical | 1557 | 0.98009 | 3 | 0 | 28 |
| people | gross_annual_income | continuous | 564 | 0.992908 | 4 | 0 | 0 |
| people | employment_status | categorical | 564 | 0.994681 | 0 | 0 | 3 |
| households | non_mortgage_outstanding_total | continuous | 316 | 0.996835 | 1 | 0 | 0 |
| households | risk_tolerance | categorical | 316 | 0.996835 | 0 | 0 | 1 |
| households | tax_bracket_band | categorical | 316 | 0.996835 | 1 | 0 | 0 |
| income_lines | amount_annualized | continuous | 662 | 0.998489 | 0 | 0 | 1 |
| income_lines | frequency | categorical | 662 | 0.998489 | 0 | 0 | 1 |
| assets | value | continuous | 1557 | 1 | 0 | 0 | 0 |
| income_lines | owner | categorical | 662 | 1 | 0 | 0 | 0 |
| income_lines | source_type | categorical | 662 | 1 | 0 | 0 | 0 |
| people | client_no | integer | 564 | 1 | 0 | 0 | 0 |
| people | role | categorical | 564 | 1 | 0 | 0 | 0 |
| households | annual_household_gross_income | continuous | 316 | 1 | 0 | 0 | 0 |
| households | country | categorical | 316 | 1 | 0 | 0 | 0 |
| households | investable_assets_total | continuous | 316 | 1 | 0 | 0 | 0 |
| households | loan_outstanding_total | continuous | 316 | 1 | 0 | 0 | 0 |
| households | marital_status | categorical | 316 | 1 | 0 | 0 | 0 |
| households | market | categorical | 316 | 1 | 0 | 0 | 0 |
| households | monthly_debt_cost_total | continuous | 316 | 1 | 0 | 0 | 0 |

## Missing extracted: why?

Missing extracted happens for two different reasons: (a) **record pairing failed** (GT record exists but no extracted record matched its primary key), and (b) **within a paired record**, extracted left a specific field empty.

### Top missing due to unpaired records (gt_only)

| entity | field | field_type | n_total | n_missing_extracted_gt_only | n_missing_extracted |
| --- | --- | --- | --- | --- | --- |
| assets | provider_type | categorical | 850 | 0 | 18 |
| people | occupation_group | categorical | 328 | 0 | 4 |
| people | gross_annual_income | continuous | 564 | 0 | 4 |
| assets | subtype | categorical | 1557 | 0 | 3 |
| households | non_mortgage_outstanding_total | continuous | 316 | 0 | 1 |
| households | tax_bracket_band | categorical | 316 | 0 | 1 |
| assets | owner | categorical | 359 | 0 | 0 |
| assets | is_joint | boolean | 359 | 0 | 0 |
| assets | asset_type | categorical | 1557 | 0 | 0 |
| people | employment_status | categorical | 564 | 0 | 0 |
| households | risk_tolerance | categorical | 316 | 0 | 0 |
| income_lines | amount_annualized | continuous | 662 | 0 | 0 |
| income_lines | frequency | categorical | 662 | 0 | 0 |
| assets | value | continuous | 1557 | 0 | 0 |
| income_lines | owner | categorical | 662 | 0 | 0 |
| income_lines | source_type | categorical | 662 | 0 | 0 |
| people | client_no | integer | 564 | 0 | 0 |
| people | role | categorical | 564 | 0 | 0 |
| households | annual_household_gross_income | continuous | 316 | 0 | 0 |
| households | country | categorical | 316 | 0 | 0 |

### Top missing within paired records (both)

| entity | field | field_type | n_total | n_missing_extracted_within_paired | n_missing_extracted |
| --- | --- | --- | --- | --- | --- |
| assets | provider_type | categorical | 850 | 18 | 18 |
| people | occupation_group | categorical | 328 | 4 | 4 |
| people | gross_annual_income | continuous | 564 | 4 | 4 |
| assets | subtype | categorical | 1557 | 3 | 3 |
| households | non_mortgage_outstanding_total | continuous | 316 | 1 | 1 |
| households | tax_bracket_band | categorical | 316 | 1 | 1 |
| assets | owner | categorical | 359 | 0 | 0 |
| assets | is_joint | boolean | 359 | 0 | 0 |
| assets | asset_type | categorical | 1557 | 0 | 0 |
| people | employment_status | categorical | 564 | 0 | 0 |
| households | risk_tolerance | categorical | 316 | 0 | 0 |
| income_lines | amount_annualized | continuous | 662 | 0 | 0 |
| income_lines | frequency | categorical | 662 | 0 | 0 |
| assets | value | continuous | 1557 | 0 | 0 |
| income_lines | owner | categorical | 662 | 0 | 0 |
| income_lines | source_type | categorical | 662 | 0 | 0 |
| people | client_no | integer | 564 | 0 | 0 |
| people | role | categorical | 564 | 0 | 0 |
| households | annual_household_gross_income | continuous | 316 | 0 | 0 |
| households | country | categorical | 316 | 0 | 0 |

## Common mismatch examples

| entity | field | ground_truth | extracted | count |
| --- | --- | --- | --- | --- |
| assets | owner | joint | client_1 | 13 |
| assets | asset_type | cash | retirement | 11 |
| assets | is_joint | True | False | 11 |
| assets | asset_type | brokerage | cash | 10 |
| assets | subtype | bank_account | 401k_ira | 10 |
| assets | subtype | taxable_brokerage | bank_account | 10 |
| people | occupation_group | operations | business_owner | 3 |
| assets | asset_type | cash | alternatives | 3 |
| assets | asset_type | cash | brokerage | 3 |
| people | employment_status | employed | employed_full_time | 3 |
| assets | provider_type | retirement_platform | bank | 3 |
| assets | subtype | bank_account | taxable_brokerage | 3 |
| assets | provider_type | bank | brokerage | 3 |
| assets | asset_type | brokerage | alternatives | 2 |
| assets | subtype | bank_account | private_markets | 2 |
| assets | provider_type | insurance_company | bank | 2 |
| assets | provider_type | retirement_platform | advisor_platform | 2 |
| assets | subtype | taxable_brokerage | 401k_ira | 2 |
| assets | provider_type | brokerage | advisor_platform | 2 |
| assets | asset_type | brokerage | retirement | 2 |
| assets | provider_type | brokerage | bank | 2 |
| assets | provider_type | insurance_company | advisor_platform | 1 |
| people | occupation_group | exec | business_owner | 1 |
| people | occupation_group | sales | healthcare | 1 |
| people | occupation_group | professional | sales | 1 |
| people | occupation_group | professional | operations | 1 |
| people | occupation_group | professional | education | 1 |
| people | occupation_group | professional | business_owner | 1 |
| people | occupation_group | operations | sales | 1 |
| people | occupation_group | healthcare | operations | 1 |
| people | occupation_group | healthcare | finance | 1 |
| people | occupation_group | finance | professional | 1 |
| people | occupation_group | finance | inactive | 1 |
| people | occupation_group | exec | education | 1 |
| people | occupation_group | business_owner | professional | 1 |
| people | occupation_group | business_owner | operations | 1 |
| people | occupation_group | business_owner | healthcare | 1 |
| people | occupation_group | business_owner | education | 1 |
| assets | asset_type | property | retirement | 1 |
| income_lines | frequency | annual | monthly | 1 |

