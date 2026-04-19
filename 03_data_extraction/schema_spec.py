from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple


SchemaType = Literal[
    "string",
    "string_nullable",
    "string_fk",
    "categorical",
    "multichoice",
    "date",
    "date_nullable",
    "integer",
    "integer_nullable",
    "continuous",
    "boolean",
]


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: SchemaType
    allowed_values: Optional[List[str]] = None


@dataclass(frozen=True)
class EntitySpec:
    name: str
    primary_key: str
    fields: List[FieldSpec]

    def field_map(self) -> Dict[str, FieldSpec]:
        return {f.name: f for f in self.fields}


@dataclass(frozen=True)
class DataSchema:
    snapshot_date: str
    entities: Dict[str, EntitySpec]

    @staticmethod
    def load(path: Path) -> "DataSchema":
        obj = json.loads(path.read_text(encoding="utf-8"))
        snapshot_date = str(obj.get("snapshot_date") or "")
        ents = obj.get("entities")
        if not isinstance(ents, dict):
            raise ValueError("schema.json missing entities")
        out: Dict[str, EntitySpec] = {}
        for ent_name, ent in ents.items():
            if not isinstance(ent, dict):
                continue
            pk = str(ent.get("primary_key") or "").strip()
            fields_raw = ent.get("fields")
            if not pk or not isinstance(fields_raw, list):
                continue
            fields: List[FieldSpec] = []
            for fr in fields_raw:
                if not isinstance(fr, dict):
                    continue
                fn = str(fr.get("name") or "").strip()
                ft = str(fr.get("type") or "").strip()
                if not fn or not ft:
                    continue

                allowed_values_raw = fr.get("allowed_values")
                if allowed_values_raw is None:
                    # Common alternative key name.
                    allowed_values_raw = fr.get("enum")

                allowed_values: Optional[List[str]] = None
                if isinstance(allowed_values_raw, list):
                    vals: List[str] = []
                    for x in allowed_values_raw:
                        if x is None:
                            continue
                        s = str(x).strip()
                        if s:
                            vals.append(s)
                    if vals:
                        # de-dup while preserving order
                        seen: set[str] = set()
                        out_vals: List[str] = []
                        for v in vals:
                            if v in seen:
                                continue
                            seen.add(v)
                            out_vals.append(v)
                        allowed_values = out_vals
                # Type will be validated downstream.
                fields.append(FieldSpec(name=fn, type=ft, allowed_values=allowed_values))  # type: ignore[arg-type]
            out[str(ent_name)] = EntitySpec(name=str(ent_name), primary_key=pk, fields=fields)
        if not out:
            raise ValueError("No entities parsed from schema.json")
        return DataSchema(snapshot_date=snapshot_date, entities=out)

    def entity(self, name: str) -> EntitySpec:
        if name not in self.entities:
            raise KeyError(f"Unknown entity: {name}")
        return self.entities[name]


DEFAULT_ENTITY_ORDER: Tuple[str, ...] = (
    "households",
    "people",
    "income_lines",
    "assets",
    "liabilities",
    "protection_policies",
)


def schema_compact_for_prompt(
    schema: DataSchema,
    *,
    allowed_values_by_field_path: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    allowed_values_by_field_path = allowed_values_by_field_path or {}

    out: Dict[str, Any] = {
        "snapshot_date": schema.snapshot_date,
        "entities": {},
    }
    for ent_name in DEFAULT_ENTITY_ORDER:
        ent = schema.entities.get(ent_name)
        if ent is None:
            continue
        out["entities"][ent_name] = {
            "primary_key": ent.primary_key,
            "fields": [
                {
                    **{"name": f.name, "type": f.type},
                    **(
                        {
                            "allowed_values": allowed_values_by_field_path.get(f"{ent_name}.{f.name}")
                            or f.allowed_values
                        }
                        if (
                            (allowed_values_by_field_path.get(f"{ent_name}.{f.name}") or f.allowed_values)
                            and f.type in {"categorical", "multichoice"}
                        )
                        else {}
                    ),
                }
                for f in ent.fields
            ],
        }
    # Include any remaining entities (if schema grows).
    for ent_name, ent in schema.entities.items():
        if ent_name in out["entities"]:
            continue
        out["entities"][ent_name] = {
            "primary_key": ent.primary_key,
            "fields": [
                {
                    **{"name": f.name, "type": f.type},
                    **(
                        {
                            "allowed_values": allowed_values_by_field_path.get(f"{ent_name}.{f.name}")
                            or f.allowed_values
                        }
                        if (
                            (allowed_values_by_field_path.get(f"{ent_name}.{f.name}") or f.allowed_values)
                            and f.type in {"categorical", "multichoice"}
                        )
                        else {}
                    ),
                }
                for f in ent.fields
            ],
        }
    return out
