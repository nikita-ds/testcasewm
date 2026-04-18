from __future__ import annotations
from pathlib import Path
import os
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "artifacts"
TABLES = ART / "tables"

def main():
    hh = pd.read_csv(TABLES / "households.csv")
    feats = hh[[
        "annual_household_gross_income","monthly_expenses_total","expense_to_income_ratio","annual_alimony_paid",
        "loan_outstanding_total","monthly_debt_cost_total","monthly_mortgage_payment_total","monthly_non_mortgage_payment_total",
        "mortgage_payment_to_income_ratio","property_value_total","investable_assets_total","retirement_assets_total",
        "cash_and_cashlike_total","alternatives_total","net_worth_proxy","num_dependants"
    ]].fillna(0.0).astype(float)

    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset

    seed = int(os.environ.get("SYNTH_SEED", "42"))

    X = feats.values
    mean = X.mean(axis=0, keepdims=True)
    std = X.std(axis=0, keepdims=True)
    std[std == 0] = 1.0
    Xs = (X - mean) / std

    X_tensor=torch.tensor(Xs, dtype=torch.float32)
    dl=DataLoader(TensorDataset(X_tensor), batch_size=128, shuffle=True)

    class AE(nn.Module):
        def __init__(self, input_dim):
            super().__init__()
            self.encoder=nn.Sequential(nn.Linear(input_dim,32), nn.ReLU(), nn.Linear(32,16), nn.ReLU(), nn.Linear(16,4))
            self.decoder=nn.Sequential(nn.Linear(4,16), nn.ReLU(), nn.Linear(16,32), nn.ReLU(), nn.Linear(32,input_dim))
        def forward(self,x): return self.decoder(self.encoder(x))

    model=AE(Xs.shape[1]); opt=torch.optim.Adam(model.parameters(), lr=1e-3); loss_fn=nn.MSELoss()
    model.train()
    for _ in range(40):
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
            n_estimators=250,
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

    hh[["household_id", "scenario", "wealth_segment", "reconstruction_error", "isolation_forest_score"]].to_csv(
        TABLES / "anomaly_scores.csv", index=False
    )

    hh.sort_values("reconstruction_error", ascending=False).head(5).to_csv(
        TABLES / "top5_anomalous_households.csv", index=False
    )
    if hh["isolation_forest_score"].notna().any():
        hh.sort_values("isolation_forest_score", ascending=False).head(5).to_csv(
            TABLES / "top5_anomalous_households_iforest.csv", index=False
        )

    print("Wrote anomaly scores + top-5 (AE and IsolationForest)")

if __name__ == "__main__":
    main()
