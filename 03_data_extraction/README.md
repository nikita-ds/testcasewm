# 03_data_extraction

Пайплайн `03` строит ground truth пары для realism-passed диалогов, запускает LLM extraction, сравнивает extraction с ground truth и пишет метрики, графики, таблицы ошибок и markdown report.

Методологические детали описаны в [`approach.md`](approach.md).

## Быстрый запуск через Docker

Из папки `03_data_extraction`:

```bash
docker compose up --build
```

Это запускает `run_pipeline.py` и выполняет весь pipeline:

1. export grounded profiles из evidence-файлов, если включен `AUTO_EXPORT_GROUNDED_PROFILES`;
2. построение `ground_truth_pairs.jsonl` и базовых графиков набора;
3. LLM extraction по `.txt` диалогам;
4. сборку `joint_dataset.jsonl`;
5. scoring и `merged/merged_ground_truth_extracted.jsonl`;
6. discrepancy analysis;
7. финальную `metrics_table.txt`.

## Локальный запуск

Нужны зависимости из `requirements.txt` и `OPENAI_API_KEY` в окружении или в `.env`.

```bash
python3 run_pipeline.py
```

Если нужно только построить пары и графики, без extraction/evaluation:

```bash
python3 run.py --reports-only
```

Если нужно запустить extraction отдельно:

```bash
python3 extract_from_dialogs.py \
  --dialogs-dir ../02_dialogs_generation/artifacts/dialogs/realism_passed \
  --out-dir artifacts/extracted \
  --workers 20
```

Если нужно пересчитать evaluation по уже готовым extracted JSON:

```bash
python3 build_joint_dataset.py
python3 evaluate_extraction.py
python3 analyze_discrepancies.py
python3 compute_metrics.py
```

## Основные переменные окружения

`REALISM_PASSED_DIR` - папка с `DIALOG_*.txt`. По умолчанию:

```text
../02_dialogs_generation/artifacts/dialogs/realism_passed
```

`FINANCIAL_PROFILES_JSON` - полный synthetic profiles JSON. По умолчанию:

```text
../02_dialogs_generation/artifacts/financial_profiles.json
```

`GROUNDED_PROFILES_JSON` - sparse dialog-grounded profiles JSON. Если файл существует, `run.py` использует его как GT для соответствующих households.

`OUTPUT_DIR` - корневая папка артефактов. По умолчанию:

```text
./artifacts
```

`PAIRS_BASENAME` - имя файла пар внутри `OUTPUT_DIR`. По умолчанию:

```text
ground_truth_pairs.jsonl
```

`AUTO_EXPORT_GROUNDED_PROFILES` - автоматически собрать grounded profiles перед построением пар. Default: `1`.

`EVIDENCE_DIALOGS_DIR` - папка с `DIALOG_*_evidence.json` для export grounded profiles.

`FORCE_REBUILD_GROUNDED_PROFILES` - пересобрать `GROUNDED_PROFILES_JSON`, даже если файл уже есть. Default: `0`.

`INCLUDE_APPROXIMATE_GROUNDED` - включать evidence items со статусом `approximate`. Default: `0`.

`EXTRACTION_LIMIT` - лимит диалогов для extraction/evaluation. `0` значит все.

`EXTRACTION_WORKERS` - число параллельных extraction workers.

`EXTRACTION_FORCE_REEXTRACT` - если `1`, перезаписывать extraction вместо `--skip-existing` поведения.

`OPENAI_MODEL` - модель extractor. По умолчанию в коде `gpt-5.2`.

`OPENAI_TIMEOUT_S` и `OPENAI_MAX_RETRIES` - настройки OpenAI client.

## OOS запуск

Для отложенного теста важно писать все в отдельный `OUTPUT_DIR`, чтобы не смешивать OOS с tuning artifacts.

Пример Docker run на уже подготовленной папке OOS dialogs:

```bash
docker compose run --rm \
  -e OUTPUT_DIR=/repo/03_data_extraction/artifacts/OOS \
  -e REALISM_PASSED_DIR=/repo/03_data_extraction/artifacts/OOS/dialogs_input \
  -e EVIDENCE_DIALOGS_DIR=/repo/03_data_extraction/artifacts/OOS/dialogs_input \
  -e GROUNDED_PROFILES_JSON=/repo/03_data_extraction/artifacts/OOS/grounded_financial_profiles.json \
  -e FORCE_REBUILD_GROUNDED_PROFILES=1 \
  -e AUTO_EXPORT_GROUNDED_PROFILES=1 \
  -e EXTRACTION_LIMIT=99 \
  -e EXTRACTION_FORCE_REEXTRACT=1 \
  -e EXTRACTION_WORKERS=20 \
  extract_from_dialogs
```

После OOS run полезно проверить счетчики:

```bash
python3 -c 'from pathlib import Path
root = Path("artifacts/OOS")
print("input_txt", len(list((root / "dialogs_input").glob("DIALOG_HH*.txt"))))
print("pairs", sum(1 for _ in open(root / "ground_truth_pairs.jsonl", encoding="utf-8")))
print("extracted", len(list((root / "extracted").glob("DIALOG_*.extracted.json"))))
print("joint", sum(1 for _ in open(root / "joint_dataset.jsonl", encoding="utf-8")))
print("merged", sum(1 for _ in open(root / "merged/merged_ground_truth_extracted.jsonl", encoding="utf-8")))
'
```

И отдельно проверить отсутствие overlap с tuning extracted households.

## Outputs

При стандартном запуске все пишется в `artifacts/`. При OOS или другом изолированном запуске все пишется в `OUTPUT_DIR`.

Главные файлы:

- `ground_truth_pairs.jsonl` - пары dialog + GT profile;
- `summary.json` - summary построения пар;
- `grounded_financial_profiles.json` - dialog-grounded GT, если собирался в этом output dir;
- `extracted/DIALOG_*.extracted.json` - финальные extraction outputs;
- `extracted/DIALOG_*.raw.json` - raw model outputs;
- `extracted/extracted_index.jsonl` - статус extraction по диалогам;
- `extracted/coerce_issues.json` - coercion issues;
- `extracted/coverage_aggregate.json` - coverage by extracted field;
- `joint_dataset.jsonl` - side-by-side GT/extracted dataset;
- `merged/merged_ground_truth_extracted.jsonl` - scored field-level merge;
- `merged/accuracy_report.json` - aggregate evaluation report;
- `metrics_table.txt` - верхнеуровневые метрики качества.

Графики:

- `figures/assets_hist.png`;
- `figures/income_hist.png`;
- `figures/scenario_distribution.png`;
- `figures/extraction_accuracy_hist.png`;
- `figures/discrepancy_worst_fields.png`;
- `figures/discrepancy_error_type_breakdown.png`;
- `figures/discrepancy_record_pairing.png`.

Discrepancy outputs:

- `discrepancy_summary.json`;
- `report/discrepancy_report.md`;
- `tables/discrepancy_field_stats.csv`;
- `tables/discrepancy_entity_record_pairing.csv`;
- `tables/discrepancy_record_pair_status.csv`;
- `tables/discrepancy_examples.csv`;
- `tables/value_mismatch_cells.csv`;
- `tables/discrepancy_missing_extracted_samples.csv`;
- `tables/discrepancy_extra_extracted_samples.csv`.

## Частые сценарии

Пересобрать только grounded GT:

```bash
python3 export_grounded_profiles.py \
  --dialogs-dir ../02_dialogs_generation/artifacts/dialogs \
  --out-json ../02_dialogs_generation/artifacts/grounded_financial_profiles.json
```

Запустить только reports/pairs в отдельный каталог:

```bash
OUTPUT_DIR=artifacts/debug \
REALISM_PASSED_DIR=../02_dialogs_generation/artifacts/dialogs/realism_passed \
GROUNDED_PROFILES_JSON=../02_dialogs_generation/artifacts/grounded_financial_profiles.json \
python3 run.py --reports-only
```

Запустить evaluation с кастомным tolerance:

```bash
python3 evaluate_extraction.py \
  --pairs artifacts/ground_truth_pairs.jsonl \
  --extracted-dir artifacts/extracted \
  --out-jsonl artifacts/merged/merged_ground_truth_extracted.jsonl \
  --hist-path artifacts/figures/extraction_accuracy_hist.png \
  --numeric-rel-tol 0.01
```

Включить ID-поля в scoring:

```bash
python3 evaluate_extraction.py --include-ids
python3 analyze_discrepancies.py --include-ids
```

Обычно ID-поля не включаем: extractor оценивается по смысловым данным, а не по угадыванию synthetic primary keys.

## Notes

Для OOS/test прогонов не используйте старый `artifacts/extracted` как `--extracted-dir`. Всегда задавайте отдельный `OUTPUT_DIR` и отдельный `REALISM_PASSED_DIR`.

Если Docker видит папку через `/repo`, не используйте symlink-и на host paths вроде `/Users/...` внутри `REALISM_PASSED_DIR`: внутри контейнера такие ссылки могут быть недоступны. Для OOS input лучше копировать файлы или создавать ссылки с container-visible paths.
