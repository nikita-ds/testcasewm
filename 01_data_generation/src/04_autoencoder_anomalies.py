from __future__ import annotations
from pathlib import Path
import os
import argparse
import numpy as np
import pandas as pd

from runtime_config import AnomaliesRuntimeConfig, load_anomalies_runtime_config

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "artifacts"
TABLES = ART / "tables"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=str, default=str(ROOT / "config" / "anomalies_runtime.json"))
    ap.add_argument("--tables-dir", type=str, default=None)
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    cfg: AnomaliesRuntimeConfig = load_anomalies_runtime_config(args.config)
    if args.tables_dir is not None:
        cfg = cfg.model_copy(update={"tables_dir": str(args.tables_dir)})
    if args.seed is not None:
        cfg = cfg.model_copy(update={"seed": int(args.seed)})
    else:
        # Back-compat: allow env override if CLI not provided.
        env_seed = os.environ.get("SYNTH_SEED")
        if env_seed is not None and str(env_seed).strip() != "":
            cfg = cfg.model_copy(update={"seed": int(env_seed)})

    tables_dir = (ROOT / cfg.tables_dir).resolve() if not Path(cfg.tables_dir).is_absolute() else Path(cfg.tables_dir)

    hh = pd.read_csv(tables_dir / "households.csv")
    feats = hh[cfg.features].fillna(0.0).astype(float)

    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset

    seed = int(cfg.seed)

    X = feats.values
    mean = X.mean(axis=0, keepdims=True)
    std = X.std(axis=0, keepdims=True)
    std[std == 0] = 1.0
    Xs = (X - mean) / std

    X_tensor=torch.tensor(Xs, dtype=torch.float32)
    dl=DataLoader(TensorDataset(X_tensor), batch_size=int(cfg.ae_batch_size), shuffle=True)

    class AE(nn.Module):
        def __init__(self, input_dim):
            super().__init__()
            h1, h2, z = [int(x) for x in cfg.ae_hidden_dims]
            self.encoder=nn.Sequential(nn.Linear(input_dim,h1), nn.ReLU(), nn.Linear(h1,h2), nn.ReLU(), nn.Linear(h2,z))
            self.decoder=nn.Sequential(nn.Linear(z,h2), nn.ReLU(), nn.Linear(h2,h1), nn.ReLU(), nn.Linear(h1,input_dim))
        def forward(self,x): return self.decoder(self.encoder(x))

    model=AE(Xs.shape[1]); opt=torch.optim.Adam(model.parameters(), lr=float(cfg.ae_learning_rate)); loss_fn=nn.MSELoss()
    model.train()
    for _ in range(int(cfg.ae_epochs)):
        for (xb,) in dl:
            opt.zero_grad(); recon=model(xb); loss=loss_fn(recon, xb); loss.backward(); opt.step()
    model.eval()
    with torch.no_grad():
        recon=model(X_tensor).numpy()
    err = ((Xs - recon) ** 2).mean(axis=1)
    hh["reconstruction_error"] = err

    # IsolationForest (tree-based) anomaly score.
    try:
        from sklearn.ensemble import IsolationForest

        iso = IsolationForest(
            n_estimators=int(cfg.iforest_n_estimators),
            random_state=seed,
            n_jobs=-1,
        )
        iso.fit(Xs)
        # score_samples: higher means more normal; invert to make higher = more anomalous.
        iso_score = -iso.score_samples(Xs)
        hh["isolation_forest_score"] = iso_score
    except Exception as e:
        hh["isolation_forest_score"] = np.nan
        print("IsolationForest unavailable:", repr(e))

    hh[["household_id", "scenario", "reconstruction_error", "isolation_forest_score"]].to_csv(
        tables_dir / "anomaly_scores.csv", index=False
    )

    hh.sort_values("reconstruction_error", ascending=False).head(5).to_csv(
        tables_dir / "top5_anomalous_households.csv", index=False
    )
    if hh["isolation_forest_score"].notna().any():
        hh.sort_values("isolation_forest_score", ascending=False).head(5).to_csv(
            tables_dir / "top5_anomalous_households_iforest.csv", index=False
        )

    print("Wrote anomaly scores + top-5 (AE and IsolationForest)")

if __name__ == "__main__":
    main()
