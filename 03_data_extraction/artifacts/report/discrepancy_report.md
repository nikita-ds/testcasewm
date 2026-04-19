# Extraction discrepancy analysis

## Overall

- Households analyzed: **316**
- Scored cells: **21532**
- Match rate (cells): **0.989**

### Error breakdown (scored cells)

- Missing extracted: **54**
- Extra extracted: **0**
- Value mismatch: **183**

## Record pairing by entity

| entity | record_pairs | records_both_present | records_gt_only | records_ex_only | both_present_rate | sample_gt_only_keys | sample_ex_only_keys |
| --- | --- | --- | --- | --- | --- | --- | --- |
| income_lines | 849 | 662 | 0 | 187 | 0.779741 |  | HH000018_I1,HH000018_I2,HH000059_I1,HH000059_I2,inc_4 |
| liabilities | 317 | 272 | 0 | 45 | 0.858044 |  | HH000018_L1,HH000018_L2,HH000018_L3,HH000226_L1,HH000226_L2 |
| protection_policies | 199 | 190 | 0 | 9 | 0.954774 |  | P1,P2,P3,POL_HH003182_1,POL_HH003182_2 |
| people | 568 | 560 | 4 | 4 | 0.985915 | HH000188_P1,HH000188_P2,HH000630_P1,HH000630_P2 | client_1,client_2,client_1,client_2 |
| assets | 1566 | 1557 | 0 | 9 | 0.994253 |  | HH001292_A6,HH001435_A4,HH001908_A6,HH002171_A5,HH002537_A2 |
| households | 316 | 316 | 0 | 0 | 1 |  |  |

## Worst fields (by match rate)

| entity | field | field_type | n_total | match_rate | n_missing_extracted | n_extra_extracted | n_value_mismatch |
| --- | --- | --- | --- | --- | --- | --- | --- |
| people | occupation_group | categorical | 469 | 0.925373 | 8 | 0 | 27 |
| assets | provider_type | categorical | 1030 | 0.95534 | 21 | 0 | 25 |
| assets | asset_type | categorical | 1557 | 0.978163 | 0 | 0 | 34 |
| assets | is_joint | boolean | 1557 | 0.979448 | 0 | 0 | 32 |
| assets | owner | categorical | 1557 | 0.98009 | 0 | 0 | 31 |
| assets | subtype | categorical | 1557 | 0.98009 | 3 | 0 | 28 |
| people | gross_annual_income | continuous | 564 | 0.985816 | 8 | 0 | 0 |
| people | employment_status | categorical | 564 | 0.987589 | 4 | 0 | 3 |
| people | client_no | integer | 564 | 0.992908 | 4 | 0 | 0 |
| people | role | categorical | 564 | 0.992908 | 4 | 0 | 0 |
| households | non_mortgage_outstanding_total | continuous | 316 | 0.996835 | 1 | 0 | 0 |
| households | risk_tolerance | categorical | 316 | 0.996835 | 0 | 0 | 1 |
| households | tax_bracket_band | categorical | 316 | 0.996835 | 1 | 0 | 0 |
| income_lines | amount_annualized | continuous | 662 | 0.998489 | 0 | 0 | 1 |
| income_lines | frequency | categorical | 662 | 0.998489 | 0 | 0 | 1 |
| assets | value | continuous | 1557 | 1 | 0 | 0 | 0 |
| income_lines | owner | categorical | 662 | 1 | 0 | 0 | 0 |
| income_lines | source_type | categorical | 662 | 1 | 0 | 0 | 0 |
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
| people | occupation_group | categorical | 469 | 4 | 8 |
| people | gross_annual_income | continuous | 564 | 4 | 8 |
| people | employment_status | categorical | 564 | 4 | 4 |
| people | client_no | integer | 564 | 4 | 4 |
| people | role | categorical | 564 | 4 | 4 |
| assets | provider_type | categorical | 1030 | 0 | 21 |
| assets | subtype | categorical | 1557 | 0 | 3 |
| households | non_mortgage_outstanding_total | continuous | 316 | 0 | 1 |
| households | tax_bracket_band | categorical | 316 | 0 | 1 |
| assets | asset_type | categorical | 1557 | 0 | 0 |
| assets | is_joint | boolean | 1557 | 0 | 0 |
| assets | owner | categorical | 1557 | 0 | 0 |
| households | risk_tolerance | categorical | 316 | 0 | 0 |
| income_lines | amount_annualized | continuous | 662 | 0 | 0 |
| income_lines | frequency | categorical | 662 | 0 | 0 |
| assets | value | continuous | 1557 | 0 | 0 |
| income_lines | owner | categorical | 662 | 0 | 0 |
| income_lines | source_type | categorical | 662 | 0 | 0 |
| households | annual_household_gross_income | continuous | 316 | 0 | 0 |
| households | country | categorical | 316 | 0 | 0 |

### Top missing within paired records (both)

| entity | field | field_type | n_total | n_missing_extracted_within_paired | n_missing_extracted |
| --- | --- | --- | --- | --- | --- |
| assets | provider_type | categorical | 1030 | 21 | 21 |
| people | occupation_group | categorical | 469 | 4 | 8 |
| people | gross_annual_income | continuous | 564 | 4 | 8 |
| assets | subtype | categorical | 1557 | 3 | 3 |
| households | non_mortgage_outstanding_total | continuous | 316 | 1 | 1 |
| households | tax_bracket_band | categorical | 316 | 1 | 1 |
| people | employment_status | categorical | 564 | 0 | 4 |
| people | client_no | integer | 564 | 0 | 4 |
| people | role | categorical | 564 | 0 | 4 |
| assets | asset_type | categorical | 1557 | 0 | 0 |
| assets | is_joint | boolean | 1557 | 0 | 0 |
| assets | owner | categorical | 1557 | 0 | 0 |
| households | risk_tolerance | categorical | 316 | 0 | 0 |
| income_lines | amount_annualized | continuous | 662 | 0 | 0 |
| income_lines | frequency | categorical | 662 | 0 | 0 |
| assets | value | continuous | 1557 | 0 | 0 |
| income_lines | owner | categorical | 662 | 0 | 0 |
| income_lines | source_type | categorical | 662 | 0 | 0 |
| households | annual_household_gross_income | continuous | 316 | 0 | 0 |
| households | country | categorical | 316 | 0 | 0 |

## Common mismatch examples

| entity | field | ground_truth | extracted | count |
| --- | --- | --- | --- | --- |
| assets | is_joint | False | True | 21 |
| assets | owner | joint | client_1 | 13 |
| assets | owner | client_1 | joint | 12 |
| assets | asset_type | cash | retirement | 11 |
| assets | is_joint | True | False | 11 |
| assets | subtype | bank_account | 401k_ira | 10 |
| assets | asset_type | brokerage | cash | 10 |
| assets | subtype | taxable_brokerage | bank_account | 10 |
| assets | provider_type | advisor_platform | bank | 6 |
| assets | provider_type | retirement_platform | bank | 4 |
| people | employment_status | employed | employed_full_time | 3 |
| assets | provider_type | retirement_platform | advisor_platform | 3 |
| assets | owner | client_2 | client_1 | 3 |
| assets | owner | client_2 | joint | 3 |
| assets | asset_type | cash | brokerage | 3 |
| assets | asset_type | cash | alternatives | 3 |
| assets | provider_type | bank | brokerage | 3 |
| assets | subtype | bank_account | taxable_brokerage | 3 |
| people | occupation_group | operations | business_owner | 3 |
| people | occupation_group | inactive | business_owner | 2 |
| assets | subtype | bank_account | private_markets | 2 |
| assets | asset_type | brokerage | alternatives | 2 |
| assets | subtype | taxable_brokerage | 401k_ira | 2 |
| assets | provider_type | insurance_company | bank | 2 |
| assets | asset_type | brokerage | retirement | 2 |
| assets | provider_type | brokerage | bank | 2 |
| assets | provider_type | brokerage | advisor_platform | 2 |
| people | occupation_group | healthcare | operations | 1 |
| assets | asset_type | property | retirement | 1 |
| people | occupation_group | inactive | exec | 1 |
| people | occupation_group | inactive | finance | 1 |
| people | occupation_group | inactive | operations | 1 |
| people | occupation_group | inactive | professional | 1 |
| people | occupation_group | professional | business_owner | 1 |
| people | occupation_group | operations | sales | 1 |
| people | occupation_group | finance | professional | 1 |
| people | occupation_group | professional | education | 1 |
| people | occupation_group | professional | operations | 1 |
| people | occupation_group | professional | sales | 1 |
| people | occupation_group | retired | operations | 1 |

