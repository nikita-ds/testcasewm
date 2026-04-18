from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np


class ScenarioConfigError(KeyError):
    pass


def list_scenarios(priors: Dict[str, Any]) -> List[str]:
    gp = priors.get("generator_params") or {}
    scenarios = list(gp.get("scenarios") or priors.get("scenario_catalog") or [])
    if not scenarios:
        raise ScenarioConfigError("Missing generator_params.scenarios (or scenario_catalog)")
    return [str(s) for s in scenarios]


def scenario_weights(priors: Dict[str, Any], n_scenarios: int) -> np.ndarray:
    gp = priors.get("generator_params") or {}
    w = gp.get("scenario_weights")
    if w is None:
        raise ScenarioConfigError("Missing generator_params.scenario_weights")
    weights = np.asarray(w, dtype=float)
    if weights.shape != (n_scenarios,):
        raise ScenarioConfigError(
            f"scenario_weights length {weights.shape} does not match scenarios {n_scenarios}"
        )
    weights = weights / weights.sum()
    return weights


def sample_scenario(priors: Dict[str, Any], rng: np.random.Generator) -> str:
    scenarios = list_scenarios(priors)
    weights = scenario_weights(priors, len(scenarios))
    return str(rng.choice(scenarios, p=weights))
