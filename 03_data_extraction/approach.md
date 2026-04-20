# Approach

Документ описывает, как устроен пайплайн `03_data_extraction`: как мы строим ground truth, как извлекаем структурированные данные из диалогов, как считаем ошибки и какие артефакты используем для анализа качества.

## 1. Ground Truth

Цель ground truth в `03` - получить для каждого диалога пару:

- `dialog`: текст диалога advisor-client;
- `profile`: структурированный эталонный профиль household, с которым будет сравниваться extractor.

Основной файл пар создается скриптом `run.py` и записывается в:

```text
artifacts/ground_truth_pairs.jsonl
```

или в другой каталог, если задан `OUTPUT_DIR`.

### Источники данных

Пайплайн читает:

- диалоги из `REALISM_PASSED_DIR`;
- полный синтетический профиль из `FINANCIAL_PROFILES_JSON`;
- опциональный dialog-grounded профиль из `GROUNDED_PROFILES_JSON`.

Если для household есть запись в `GROUNDED_PROFILES_JSON`, она используется как ground truth вместо полного синтетического профиля. Это важно: в диалоге может быть озвучена только часть полей полного профиля, и extractor не должен штрафоваться за то, что не извлек поле, которого реально не было в тексте.

### Dialog-grounded GT

Dialog-grounded profile строится из `DIALOG_*_evidence.json` с помощью:

```bash
python export_grounded_profiles.py \
  --dialogs-dir <dir-with-evidence-files> \
  --out-json <grounded_financial_profiles.json>
```

По умолчанию включаются только evidence items со статусом `present`. Это означает: поле попадает в grounded GT только если оно было явно найдено в диалоге. Если нужно включить приблизительные факты, можно задать `INCLUDE_APPROXIMATE_GROUNDED=1`, но для честной оценки extractor по умолчанию это выключено.

`run_pipeline.py` может собрать grounded GT автоматически перед построением пар:

- `AUTO_EXPORT_GROUNDED_PROFILES=1`;
- `EVIDENCE_DIALOGS_DIR=<dir>`;
- `GROUNDED_PROFILES_JSON=<out-json>`;
- `FORCE_REBUILD_GROUNDED_PROFILES=1`, если надо пересобрать файл.

### Что попадает в пары

Каждая строка `ground_truth_pairs.jsonl` содержит:

- `household_id`;
- `dialog_id`;
- `scenario`;
- `profile`;
- `dialog`;
- `ground_truth_is_grounded`.

`ground_truth_is_grounded=true` означает, что denominator при scoring будет учитывать только поля, присутствующие в grounded GT. Это защищает оценку от штрафа за неозвученные в диалоге факты.

Для диагностических графиков `run.py` использует полный профиль, даже если scoring использует grounded GT. Так распределения income/assets/scenario остаются стабильными и отражают сгенерированный набор households.

## 2. Extraction

Extraction выполняется скриптом `extract_from_dialogs.py`. На вход он получает `.txt` диалоги, схему данных и priors, а на выход пишет один структурированный JSON на диалог:

```text
artifacts/extracted/DIALOG_<household_id>.extracted.json
```

### Модель и prompt

Модель задается через `OPENAI_MODEL` или аргумент `--model`. По умолчанию сейчас используется:

```text
gpt-5.2
```

Системный prompt находится в:

```text
prompts/extraction_system_prompt.txt
```

В prompt подставляется compact schema из `schema.json`. Для categorical/multichoice полей также подставляются allowed values из schema и priors, чтобы модель выбирала допустимые значения, а не изобретала новые.

Главные правила prompt:

- использовать только факты, сказанные или сильно подразумеваемые в диалоге;
- если поле не упомянуто, пропустить его;
- если сущность явно есть, создать запись даже при частично неизвестных полях;
- для чисел возвращать числа, для boolean - boolean;
- для дат использовать `YYYY-MM-DD`;
- для ranges использовать midpoint, если позже нет более точного значения;
- для owner использовать `joint` только при явном joint/shared/both names;
- для provider_type выбирать underlying institution, а не платформу-агрегатор, если она только показывает актив.

### Извлекаемые сущности и поля

Extractor возвращает top-level JSON object с ключами:

- `households`;
- `people`;
- `income_lines`;
- `assets`;
- `liabilities`;
- `protection_policies`.

Поля берутся из `01_data_generation/config/schema.json`.

`households`:

```text
household_id, scenario, country, market, marital_status, residence_state, move_in_date,
primary_age, primary_years_to_retirement, secondary_age, secondary_years_to_retirement,
num_adults, num_dependants, youngest_child_dob, oldest_child_dob,
annual_household_gross_income, monthly_expenses_total, expense_to_income_ratio,
annual_alimony_paid, has_mortgage_or_loan, loan_outstanding_total,
mortgage_outstanding_total, non_mortgage_outstanding_total, monthly_debt_cost_total,
monthly_mortgage_payment_total, monthly_non_mortgage_payment_total,
mortgage_payment_to_income_ratio, property_value_total, investable_assets_total,
retirement_assets_total, cash_and_cashlike_total, alternatives_total, net_worth_proxy,
risk_tolerance, investment_objectives, tax_bracket_band, client_segment,
household_head_email, household_head_mobile_phone
```

`people`:

```text
person_id, household_id, client_no, role, title, first_name, middle_names, last_name,
known_as, pronouns, place_of_birth, nationality, gender, legal_sex, home_phone,
mobile_phone, email_address, date_of_birth, employment_status, employment_started,
desired_retirement_age, occupation_group, smoker, state_of_health, gross_annual_income
```

`income_lines`:

```text
income_line_id, household_id, owner, source_type, frequency, net_or_gross, amount_annualized
```

`assets`:

```text
asset_id, household_id, owner, asset_type, subtype, provider_type, value, is_joint
```

`liabilities`:

```text
liability_id, household_id, type, monthly_cost, outstanding, interest_rate, final_payment_date
```

`protection_policies`:

```text
policy_id, household_id, owner, policy_type, monthly_cost, amount_assured, assured_until
```

### Post-processing extraction

После LLM-вызова extractor делает несколько deterministic шагов:

- unwrap common wrappers вроде `{"result": ...}` или `{"extracted": ...}`;
- coerce values к типам схемы;
- drop unknown fields/entities;
- normalize categorical values and primary-key formats;
- compute derived household fields from liabilities where applicable;
- сохранить raw попытки и финальный extracted JSON.

Если первая попытка вернула плохую структуру или пустой extraction, скрипт повторяет вызов до `EXTRACTION_RETRY_LIMIT` раз.

### Rescue-проходы

В текущей реализации есть два targeted rescue-прохода:

- liability/protection rescue: если диалог явно содержит mortgage/loan/card/policy hints, но extractor вернул пустые `liabilities` или `protection_policies`;
- asset/owner rescue: если у assets не хватает `owner`, `is_joint`, `provider_type` или у people не хватает `occupation_group`, а в тексте есть подсказки.

Rescue не заменяет весь extraction. Он достает только узкий набор сущностей/полей и merge-ится в базовый результат, чтобы не размазывать ошибки одной части по всему профилю.

Есть также deterministic repair для специфического случая bank-type retirement asset, когда по текстовому паттерну видно, что запись должна быть cash/bank account, а не retirement.

## 3. Error Counting

Оценка выполняется `evaluate_extraction.py`, а подробный анализ ошибок - `analyze_discrepancies.py`.

### Нормализация перед сравнением

Перед scoring обе стороны нормализуются:

- ground truth profile;
- extracted profile.

Это снижает шум от разных форматов ID, categorical aliases и простых строковых расхождений.

### Сопоставление записей

Для каждой entity сначала нужно сопоставить GT records и extracted records.

Если возможно, используется primary key. Но extractor может сгенерировать нестабильные IDs, поэтому для нескольких сущностей по умолчанию включено content-based pairing:

- `income_lines`;
- `people`;
- `assets`;
- `liabilities`;
- `protection_policies`.

Content pairing использует weighted similarity по смысловым полям. Например:

- assets: owner, asset_type, subtype, provider_type, value;
- income_lines: owner, source_type, frequency, net_or_gross, amount_annualized;
- people: client_no, role, employment_status, occupation_group, first_name, gross_annual_income;
- liabilities: type, final_payment_date, monthly_cost, outstanding, interest_rate;
- protection_policies: owner, policy_type, assured_until, monthly_cost, amount_assured.

Если запись есть только в GT, это `gt_only`; если только в extraction, это `ex_only`; если обе стороны найдены, это `both`.

### Сравнение значений

Сравнение идет cell-by-cell по полям схемы.

Правила:

- numeric fields (`continuous`, `integer`, `integer_nullable`) считаются совпавшими, если отличаются не более чем на `numeric_rel_tol`; default `0.01`, то есть 1%;
- boolean сравнивается как boolean;
- date/date_nullable сравниваются строково после нормализации;
- multichoice сравнивается как отсортированное множество значений; строки могут быть разделены `|` или comma;
- остальные строковые/categorical поля сравниваются case-insensitive после trim.

Оба `None` считаются match, но scoreable denominator зависит от режима GT.

### Grounded-aware denominator

Если `ground_truth_is_grounded=true`, поле идет в denominator только если оно реально присутствовало в grounded GT. Это ключевое допущение для честной оценки: extractor не обязан восстанавливать то, чего не было в диалоге.

Если GT не grounded, denominator включает scoreable поля схемы независимо от того, было ли значение `None`.

### Исключения из scoring

По умолчанию не оцениваются:

- primary key fields;
- поля, заканчивающиеся на `_id`;
- поля, заканчивающиеся на `_ratio`;
- поля из `config/scoring_exclusions.json`.

Сейчас в exclusions вынесены PII/person-detail поля, которые либо не должны быть центральной целью extractor, либо создают шум:

```text
households.household_head_email
households.household_head_mobile_phone
people.title
people.middle_names
people.last_name
people.known_as
people.pronouns
people.place_of_birth
people.nationality
people.gender
people.legal_sex
people.home_phone
people.mobile_phone
people.email_address
people.date_of_birth
people.employment_started
people.desired_retirement_age
people.smoker
people.state_of_health
```

ID-поля можно включить через `--include-ids`, но для extractor quality это обычно нежелательно: нас интересует смысловая правильность, а не то, угадала ли модель synthetic primary keys.

### Типы ошибок

`analyze_discrepancies.py` раскладывает ошибки на:

- `missing_extracted`: в GT есть ожидаемое значение, extraction его не дал;
- `extra_extracted`: в GT поле не ожидалось, extraction его заполнил;
- `value_mismatch`: extraction дал значение, но оно не совпало с GT;
- record-level statuses: `both`, `gt_only`, `ex_only`, `both_missing`.

Для missing/extra дополнительно различается:

- ошибка из-за record pairing (`gt_only` / `ex_only`);
- ошибка внутри уже сопоставленной записи (`both`).

Это помогает отличать "модель пропустила весь asset" от "модель нашла asset, но ошиблась в owner".

## 4. Metrics, Tables, Figures

Пайплайн пишет несколько уровней диагностики.

### Dataset plots

`run.py` пишет:

- `figures/assets_hist.png`;
- `figures/income_hist.png`;
- `figures/scenario_distribution.png`.

Эти графики проверяют состав evaluation-набора: не перекошен ли он по wealth/income/scenario, и похож ли OOS/test набор на ожидаемую популяцию.

### Extraction accuracy

`evaluate_extraction.py` пишет:

- `merged/merged_ground_truth_extracted.jsonl`;
- `merged/accuracy_report.json`;
- `figures/extraction_accuracy_hist.png`.

`accuracy_report.json` содержит:

- число households;
- число scored households;
- `numeric_rel_tol`;
- `include_ids`;
- `mean_fraction`.

Histogram показывает распределение household-level accuracy: видно, это много мелких ошибок по всем households или несколько тяжелых outliers.

### Discrepancy analysis

`analyze_discrepancies.py` пишет:

- `discrepancy_summary.json`;
- `report/discrepancy_report.md`;
- `tables/discrepancy_field_stats.csv`;
- `tables/discrepancy_entity_record_pairing.csv`;
- `tables/discrepancy_record_pair_status.csv`;
- `tables/discrepancy_examples.csv`;
- `tables/value_mismatch_cells.csv`;
- `tables/discrepancy_missing_extracted_samples.csv`;
- `tables/discrepancy_extra_extracted_samples.csv`;
- `figures/discrepancy_worst_fields.png`;
- `figures/discrepancy_error_type_breakdown.png`;
- `figures/discrepancy_record_pairing.png`.

Как читать эти артефакты:

- `discrepancy_report.md` - быстрый human-readable обзор;
- `discrepancy_field_stats.csv` - главный файл для ранжирования проблемных полей;
- `value_mismatch_cells.csv` - лучший файл для точечной отладки конкретных неправильных значений;
- `discrepancy_entity_record_pairing.csv` - показывает, где проблема не в значении поля, а в пропущенных/лишних records;
- `discrepancy_error_type_breakdown.png` - помогает понять, что доминирует: missing, extra или mismatches;
- `discrepancy_worst_fields.png` - показывает самые слабые поля;
- `discrepancy_record_pairing.png` - показывает record-level recall/precision по entity.

### Final metrics table

`compute_metrics.py` пишет:

```text
metrics_table.txt
```

В нем два блока:

- доля диалогов с `100%`, `>=95%`, `>=90%` correct fields;
- per-entity rates: missed, errors, invented, total cells.

Эта таблица удобна как верхнеуровневый checkpoint для OOS/test прогона. Для поиска причин надо идти ниже: сначала в `discrepancy_report.md`, затем в CSV tables.

## 5. OOS/Test Discipline

Для честного отложенного теста важно:

- генерировать OOS dialogs по households, которые не участвовали в настройке extractor/evaluator;
- писать OOS outputs в отдельный `OUTPUT_DIR`, например `artifacts/OOS`;
- не смешивать extracted JSON, merged files, figures и metrics с tuning artifacts;
- использовать тот же код, тот же prompt, те же scoring exclusions и те же thresholds;
- явно проверять отсутствие overlap household IDs между tuning extracted set и OOS extracted set.

Текущий `run_pipeline.py` поддерживает это через `OUTPUT_DIR`, `REALISM_PASSED_DIR`, `EVIDENCE_DIALOGS_DIR` и `GROUNDED_PROFILES_JSON`.
