# Extraction discrepancy analysis

## Overall

- Households analyzed: **316**
- Scored cells: **20597**
- Match rate (cells): **0.957**

### Error breakdown (scored cells)

- Missing extracted: **723**
- Extra extracted: **0**
- Value mismatch: **155**

## Record pairing by entity

| entity | record_pairs | records_both_present | records_gt_only | records_ex_only | both_present_rate | sample_gt_only_keys | sample_ex_only_keys |
| --- | --- | --- | --- | --- | --- | --- | --- |
| liabilities | 379 | 210 | 62 | 107 | 0.55409 | HH000188_L2,HH000190_L2,HH000257_L1,HH000261_L2,HH000332_L2 | liab_small_loan_1,HH000190_L1,0,1,2 |
| protection_policies | 245 | 150 | 40 | 55 | 0.612245 | HH000188_PP1,HH000409_PP1,HH000569_PP1,HH000630_PP1,HH000653_PP1 | 0,1,pol_client1_ltc_1,0,1 |
| income_lines | 858 | 662 | 0 | 196 | 0.771562 |  | HH000018_I1,HH000018_I2,HH000059_I1,HH000059_I2,inc_client2_business_owner |
| people | 581 | 547 | 17 | 17 | 0.94148 | HH000188_P1,HH000188_P2,HH000463_P1,HH000463_P2,HH000996_P1 | client_1,client_2,client_1,client_2,HH000996_client_1 |
| assets | 1568 | 1553 | 4 | 11 | 0.990434 | HH001509_A1,HH002537_A1,HH004259_A1,HH004892_A1 | HH001509_A3,HH001644_A2,HH001908_A6,HH002171_A4,HH002537_A3 |
| households | 316 | 316 | 0 | 0 | 1 |  |  |

## Worst fields (by match rate)

| entity | field | field_type | n_total | match_rate | n_missing_extracted | n_extra_extracted | n_value_mismatch |
| --- | --- | --- | --- | --- | --- | --- | --- |
| liabilities | final_payment_date | date_nullable | 250 | 0.756 | 61 | 0 | 0 |
| liabilities | interest_rate | continuous | 272 | 0.772059 | 62 | 0 | 0 |
| liabilities | monthly_cost | continuous | 272 | 0.772059 | 62 | 0 | 0 |
| liabilities | outstanding | continuous | 272 | 0.772059 | 62 | 0 | 0 |
| liabilities | type | categorical | 272 | 0.772059 | 62 | 0 | 0 |
| protection_policies | amount_assured | continuous | 190 | 0.789474 | 40 | 0 | 0 |
| protection_policies | assured_until | date_nullable | 190 | 0.789474 | 40 | 0 | 0 |
| protection_policies | monthly_cost | continuous | 190 | 0.789474 | 40 | 0 | 0 |
| protection_policies | owner | categorical | 190 | 0.789474 | 40 | 0 | 0 |
| protection_policies | policy_type | categorical | 190 | 0.789474 | 40 | 0 | 0 |
| people | occupation_group | categorical | 564 | 0.875887 | 35 | 0 | 35 |
| assets | provider_type | categorical | 1557 | 0.947977 | 45 | 0 | 36 |
| people | employment_status | categorical | 564 | 0.960993 | 21 | 0 | 1 |
| people | gross_annual_income | continuous | 564 | 0.962766 | 21 | 0 | 0 |
| assets | owner | categorical | 1557 | 0.964676 | 34 | 0 | 21 |
| people | client_no | integer | 564 | 0.969858 | 17 | 0 | 0 |
| people | role | categorical | 564 | 0.969858 | 17 | 0 | 0 |
| households | monthly_debt_cost_total | continuous | 316 | 0.971519 | 9 | 0 | 0 |
| assets | asset_type | categorical | 1557 | 0.978805 | 4 | 0 | 29 |
| assets | subtype | categorical | 1557 | 0.980732 | 5 | 0 | 25 |
| households | risk_tolerance | categorical | 316 | 0.993671 | 0 | 0 | 2 |
| assets | value | continuous | 1557 | 0.99422 | 5 | 0 | 4 |
| households | annual_household_gross_income | continuous | 316 | 0.996835 | 0 | 0 | 1 |
| households | non_mortgage_outstanding_total | continuous | 316 | 0.996835 | 1 | 0 | 0 |
| income_lines | frequency | categorical | 662 | 0.998489 | 0 | 0 | 1 |

## Missing extracted: why?

Missing extracted happens for two different reasons: (a) **record pairing failed** (GT record exists but no extracted record matched its primary key), and (b) **within a paired record**, extracted left a specific field empty.

### Top missing due to unpaired records (gt_only)

| entity | field | field_type | n_total | n_missing_extracted_gt_only | n_missing_extracted |
| --- | --- | --- | --- | --- | --- |
| liabilities | interest_rate | continuous | 272 | 62 | 62 |
| liabilities | monthly_cost | continuous | 272 | 62 | 62 |
| liabilities | outstanding | continuous | 272 | 62 | 62 |
| liabilities | type | categorical | 272 | 62 | 62 |
| liabilities | final_payment_date | date_nullable | 250 | 61 | 61 |
| protection_policies | amount_assured | continuous | 190 | 40 | 40 |
| protection_policies | assured_until | date_nullable | 190 | 40 | 40 |
| protection_policies | monthly_cost | continuous | 190 | 40 | 40 |
| protection_policies | owner | categorical | 190 | 40 | 40 |
| protection_policies | policy_type | categorical | 190 | 40 | 40 |
| people | occupation_group | categorical | 564 | 17 | 35 |
| people | employment_status | categorical | 564 | 17 | 21 |
| people | gross_annual_income | continuous | 564 | 17 | 21 |
| people | client_no | integer | 564 | 17 | 17 |
| people | role | categorical | 564 | 17 | 17 |
| assets | provider_type | categorical | 1557 | 4 | 45 |
| assets | owner | categorical | 1557 | 4 | 34 |
| assets | subtype | categorical | 1557 | 4 | 5 |
| assets | value | continuous | 1557 | 4 | 5 |
| assets | asset_type | categorical | 1557 | 4 | 4 |

### Top missing within paired records (both)

| entity | field | field_type | n_total | n_missing_extracted_within_paired | n_missing_extracted |
| --- | --- | --- | --- | --- | --- |
| assets | provider_type | categorical | 1557 | 41 | 45 |
| assets | owner | categorical | 1557 | 30 | 34 |
| people | occupation_group | categorical | 564 | 18 | 35 |
| households | monthly_debt_cost_total | continuous | 316 | 9 | 9 |
| people | employment_status | categorical | 564 | 4 | 21 |
| people | gross_annual_income | continuous | 564 | 4 | 21 |
| assets | subtype | categorical | 1557 | 1 | 5 |
| assets | value | continuous | 1557 | 1 | 5 |
| households | non_mortgage_outstanding_total | continuous | 316 | 1 | 1 |
| liabilities | interest_rate | continuous | 272 | 0 | 62 |
| liabilities | monthly_cost | continuous | 272 | 0 | 62 |
| liabilities | outstanding | continuous | 272 | 0 | 62 |
| liabilities | type | categorical | 272 | 0 | 62 |
| liabilities | final_payment_date | date_nullable | 250 | 0 | 61 |
| protection_policies | amount_assured | continuous | 190 | 0 | 40 |
| protection_policies | assured_until | date_nullable | 190 | 0 | 40 |
| protection_policies | monthly_cost | continuous | 190 | 0 | 40 |
| protection_policies | owner | categorical | 190 | 0 | 40 |
| protection_policies | policy_type | categorical | 190 | 0 | 40 |
| people | client_no | integer | 564 | 0 | 17 |

## Common mismatch examples

| entity | field | ground_truth | extracted | count |
| --- | --- | --- | --- | --- |
| assets | provider_type | retirement_platform | bank | 14 |
| assets | owner | client_1 | joint | 13 |
| assets | asset_type | cash | retirement | 10 |
| assets | subtype | bank_account | 401k_ira | 9 |
| assets | provider_type | advisor_platform | bank | 6 |
| assets | asset_type | brokerage | cash | 6 |
| assets | subtype | taxable_brokerage | bank_account | 6 |
| assets | provider_type | bank | brokerage | 4 |
| assets | asset_type | cash | brokerage | 4 |
| assets | subtype | bank_account | taxable_brokerage | 4 |
| people | occupation_group | business_owner | professional | 4 |
| assets | owner | client_2 | joint | 3 |
| assets | owner | joint | client_1 | 3 |
| assets | asset_type | cash | alternatives | 3 |
| assets | subtype | taxable_brokerage | 401k_ira | 2 |
| people | occupation_group | operations | business_owner | 2 |
| assets | subtype | bank_account | private_markets | 2 |
| people | occupation_group | exec | professional | 2 |
| people | occupation_group | operations | professional | 2 |
| assets | provider_type | retirement_platform | insurance_company | 2 |
| assets | asset_type | brokerage | alternatives | 2 |
| assets | provider_type | insurance_company | advisor_platform | 2 |
| assets | provider_type | brokerage | bank | 2 |
| people | occupation_group | professional | business_owner | 2 |
| assets | asset_type | brokerage | retirement | 2 |
| assets | provider_type | insurance_company | bank | 2 |
| people | occupation_group | operations | sales | 1 |
| people | occupation_group | healthcare | operations | 1 |
| people | occupation_group | exec | business_owner | 1 |
| people | occupation_group | exec | inactive | 1 |
| people | occupation_group | finance | inactive | 1 |
| people | occupation_group | finance | professional | 1 |
| people | occupation_group | healthcare | business_owner | 1 |
| people | occupation_group | healthcare | finance | 1 |
| people | occupation_group | inactive | business_owner | 1 |
| people | occupation_group | sales | healthcare | 1 |
| people | occupation_group | healthcare | sales | 1 |
| people | occupation_group | sales | business_owner | 1 |
| people | occupation_group | operations | finance | 1 |
| people | occupation_group | retired | operations | 1 |

