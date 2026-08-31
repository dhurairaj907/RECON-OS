"""
RECON OS — Phase 6: Reproducible Training Pipeline

    python -m ai.training.train        (run from apps/api)

For each model: load dataset -> validate schema -> build features -> split
(stratified random for i.i.d. classifiers; chronological for the
time-dependent recovery-time regression) -> train -> evaluate -> save
artifact + metadata -> print metrics. Never trains on the test split. Fails
loudly (raises) if a dataset is malformed rather than silently producing a
bad model.

Every artifact records `dataset_type` and the REAL sample count actually
found in recon_dev.db at training time — never invented, never silently
mixed with synthetic rows without saying so.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score, brier_score_loss, confusion_matrix, f1_score,
    mean_absolute_error, mean_squared_error, precision_score, recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # apps/api on path when run directly

from ai.data import DATASET_TYPE_SYNTHETIC
from ai.data.real_data import extract_real_case_dataset
from ai.data.synthetic import (
    SEED, generate_case_dataset, generate_communication_trials,
    generate_customer_dataset, generate_strategy_trials,
)
from ai.features.feature_builder import (
    CASE_FEATURE_COLUMNS, DIAGNOSIS_FEATURE_COLUMNS, FEATURE_VERSION,
    build_case_features, build_customer_features, build_diagnosis_features,
)
from ai.models import churn_model, diagnosis_model, recovery_probability_model, recovery_time_model
from ai.models import strategy_ranking_model, channel_model, response_model
from ai.models.anomaly_model import AnomalyModel
from ai.models.base import ModelMetadata, ModelRegistry, STATUS_DATA_LIMITED, STATUS_EXPERIMENTAL, STATUS_READY, TabularModel, now_iso

VERSION = "v1"
MIN_REAL_SAMPLES_FOR_TRAINING = 200   # far above recon_dev.db's current ~38 cases — documents the bar honestly


def _print_header(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def _native(v):
    """numpy scalars (bool_/int64/float64 in numpy>=2 are NOT JSON-serializable
    Python bool/int/float subclasses) -> plain Python values."""
    if isinstance(v, np.generic):
        return v.item()
    return v


def _classification_metrics(y_true, y_pred, y_proba=None, positive_label=None) -> dict:
    metrics = {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision_macro": round(float(precision_score(y_true, y_pred, average="macro", zero_division=0)), 4),
        "recall_macro": round(float(recall_score(y_true, y_pred, average="macro", zero_division=0)), 4),
        "f1_macro": round(float(f1_score(y_true, y_pred, average="macro", zero_division=0)), 4),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
        "confusion_matrix_labels": [_native(v) for v in sorted(set(y_true) | set(y_pred), key=str)],
    }
    if y_proba is not None and positive_label is not None:
        try:
            y_bin = np.array([1 if v == positive_label else 0 for v in y_true])
            metrics["roc_auc"] = round(float(roc_auc_score(y_bin, y_proba)), 4)
            metrics["brier_score"] = round(float(brier_score_loss(y_bin, y_proba)), 4)
        except ValueError as e:
            metrics["roc_auc"] = None
            metrics["auc_note"] = f"undefined: {e}"
    return metrics


def _regression_metrics(y_true, y_pred) -> dict:
    return {
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 3),
        "rmse": round(float(mean_squared_error(y_true, y_pred) ** 0.5), 3),
        "mean_actual": round(float(np.mean(y_true)), 3),
    }


def _report_real_data(case_df_real: pd.DataFrame) -> None:
    n = len(case_df_real)
    print(f"Real recon_dev.db labeled cases found: {n}")
    if n < MIN_REAL_SAMPLES_FOR_TRAINING:
        print(
            f"  -> INSUFFICIENT for standalone training (need >= {MIN_REAL_SAMPLES_FOR_TRAINING}). "
            f"Training uses the SYNTHETIC dataset below; real rows are reported here honestly, "
            f"never silently mixed in or represented as production performance."
        )


# ---------------------------------------------------------------------------
def train_diagnosis(case_df: pd.DataFrame, real_n: int):
    _print_header("MODEL 1 — Payment Failure Diagnosis")
    feats = pd.DataFrame([build_diagnosis_features(r) for r in case_df.to_dict("records")])
    y = case_df["failure_category"].values

    X_train, X_test, y_train, y_test = train_test_split(feats, y, test_size=0.2, random_state=SEED, stratify=y)
    model = TabularModel(diagnosis_model.build_estimator(), diagnosis_model.NUMERIC_FEATURES,
                         diagnosis_model.CATEGORICAL_FEATURES, task="classification")
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    metrics = _classification_metrics(y_test, y_pred)
    print(f"  accuracy={metrics['accuracy']} f1_macro={metrics['f1_macro']}")

    metadata = ModelMetadata(
        model_name=diagnosis_model.MODEL_NAME, version=VERSION, training_timestamp=now_iso(),
        dataset_type=DATASET_TYPE_SYNTHETIC, feature_version=FEATURE_VERSION,
        algorithm=type(model.pipeline.named_steps["model"]).__name__,
        training_sample_count=len(X_train), validation_sample_count=len(X_test),
        metrics=metrics, status=STATUS_READY, label_classes=sorted(set(y.tolist())),
        real_sample_count=real_n,
        notes="Text-derived keyword features only (no failure_category input) — see "
              "ai/features/feature_builder.py. NOTE: near-100% accuracy here reflects that the "
              "SYNTHETIC failure-text templates use non-overlapping keyword sets per category "
              "(by construction) — this is a statement about the synthetic dataset's difficulty, "
              "NOT a claim about real-world diagnosis-text ambiguity, which is materially harder.",
    )
    ModelRegistry.save(diagnosis_model.MODEL_NAME, VERSION, model, metadata)
    print(f"  saved -> ai/artifacts/{diagnosis_model.MODEL_NAME}/{VERSION}")
    return metadata


def train_recovery_probability(case_df: pd.DataFrame, real_n: int):
    _print_header("MODEL 2 — Recovery Probability")
    feats = pd.DataFrame([build_case_features(r, failure_category=r["failure_category"]) for r in case_df.to_dict("records")])
    y = case_df["recovered"].values

    X_train, X_test, y_train, y_test = train_test_split(feats, y, test_size=0.2, random_state=SEED, stratify=y)
    model = TabularModel(recovery_probability_model.build_estimator(), recovery_probability_model.NUMERIC_FEATURES,
                         recovery_probability_model.CATEGORICAL_FEATURES, task="classification")
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    proba = model.predict_proba(X_test)[:, list(model.classes_).index(True)]
    metrics = _classification_metrics(y_test, y_pred, y_proba=proba, positive_label=True)
    print(f"  accuracy={metrics['accuracy']} roc_auc={metrics.get('roc_auc')} brier={metrics.get('brier_score')}")

    metadata = ModelMetadata(
        model_name=recovery_probability_model.MODEL_NAME, version=VERSION, training_timestamp=now_iso(),
        dataset_type=DATASET_TYPE_SYNTHETIC, feature_version=FEATURE_VERSION,
        algorithm=type(model.pipeline.named_steps["model"]).__name__,
        training_sample_count=len(X_train), validation_sample_count=len(X_test),
        metrics=metrics, status=STATUS_READY, label_classes=[False, True], real_sample_count=real_n,
    )
    ModelRegistry.save(recovery_probability_model.MODEL_NAME, VERSION, model, metadata)
    print(f"  saved -> ai/artifacts/{recovery_probability_model.MODEL_NAME}/{VERSION}")
    return metadata


def train_recovery_time(case_df: pd.DataFrame, real_n: int):
    _print_header("MODEL 3 — Recovery Time (EXPERIMENTAL)")
    recovered_df = case_df[case_df["recovered"] & case_df["recovery_hours"].notna()].sort_values("case_idx")
    if len(recovered_df) < 20:
        print("  INSUFFICIENT DATA — skipping (need >= 20 recovered rows with a time label).")
        return None

    feats = pd.DataFrame([build_case_features(r, failure_category=r["failure_category"]) for r in recovered_df.to_dict("records")])
    y = recovered_df["recovery_hours"].values

    split = int(len(feats) * 0.8)   # chronological split (sorted by case_idx) — time-dependent target
    X_train, X_test = feats.iloc[:split], feats.iloc[split:]
    y_train, y_test = y[:split], y[split:]

    model = TabularModel(recovery_time_model.build_estimator(), recovery_time_model.NUMERIC_FEATURES,
                         recovery_time_model.CATEGORICAL_FEATURES, task="regression")
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    metrics = _regression_metrics(y_test, y_pred)
    print(f"  MAE={metrics['mae']}h RMSE={metrics['rmse']}h (mean actual={metrics['mean_actual']}h)")

    metadata = ModelMetadata(
        model_name=recovery_time_model.MODEL_NAME, version=VERSION, training_timestamp=now_iso(),
        dataset_type=DATASET_TYPE_SYNTHETIC, feature_version=FEATURE_VERSION,
        algorithm=type(model.pipeline.named_steps["model"]).__name__,
        training_sample_count=len(X_train), validation_sample_count=len(X_test),
        metrics=metrics, status=STATUS_EXPERIMENTAL, real_sample_count=real_n,
        notes="recon_dev.db has too few completed recoveries with timestamps for a real-data model; "
              "trained on synthetic recovery-time assumptions only — treat as illustrative, not calibrated.",
    )
    ModelRegistry.save(recovery_time_model.MODEL_NAME, VERSION, model, metadata)
    print(f"  saved -> ai/artifacts/{recovery_time_model.MODEL_NAME}/{VERSION}")
    return metadata


def train_customer_recovery(case_df: pd.DataFrame, real_n: int):
    _print_header("MODEL 4 — Customer Recovery / Churn")
    customer_df = generate_customer_dataset(case_df)
    if len(customer_df) < 20:
        print("  INSUFFICIENT DATA — skipping.")
        return None

    feats = pd.DataFrame([build_customer_features(r) for r in customer_df.to_dict("records")])
    y = customer_df["next_case_recovered"].values

    X_train, X_test, y_train, y_test = train_test_split(feats, y, test_size=0.2, random_state=SEED, stratify=y)
    model = TabularModel(churn_model.build_estimator(), churn_model.NUMERIC_FEATURES,
                         churn_model.CATEGORICAL_FEATURES, task="classification")
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    proba = model.predict_proba(X_test)[:, list(model.classes_).index(True)]
    metrics = _classification_metrics(y_test, y_pred, y_proba=proba, positive_label=True)
    print(f"  accuracy={metrics['accuracy']} roc_auc={metrics.get('roc_auc')} (n_customers={len(customer_df)})")

    metadata = ModelMetadata(
        model_name=churn_model.MODEL_NAME, version=VERSION, training_timestamp=now_iso(),
        dataset_type=DATASET_TYPE_SYNTHETIC, feature_version=FEATURE_VERSION,
        algorithm=type(model.pipeline.named_steps["model"]).__name__,
        training_sample_count=len(X_train), validation_sample_count=len(X_test),
        metrics=metrics, status=STATUS_READY, label_classes=[False, True], real_sample_count=0,
        notes="Customer-grain aggregation; real recon_dev.db has too few repeat-customer cases to train on directly.",
    )
    ModelRegistry.save(churn_model.MODEL_NAME, VERSION, model, metadata)
    print(f"  saved -> ai/artifacts/{churn_model.MODEL_NAME}/{VERSION}")
    return metadata


def train_anomaly(case_df: pd.DataFrame):
    _print_header("MODEL 5 — Anomaly Detection (unsupervised)")
    feats = pd.DataFrame([build_case_features(r, failure_category=r["failure_category"]) for r in case_df.to_dict("records")])
    train_idx, test_idx = train_test_split(
        np.arange(len(feats)), test_size=0.2, random_state=SEED, stratify=case_df["is_anomaly_injected"].values,
    )
    model = AnomalyModel(contamination=0.03, random_state=SEED)
    model.fit(feats.iloc[train_idx])

    feats_test = feats.iloc[test_idx]
    is_anom_pred = model.predict_is_anomaly(feats_test)
    is_anom_true = case_df["is_anomaly_injected"].values[test_idx]

    tp = int(np.sum(is_anom_pred & is_anom_true))
    fp = int(np.sum(is_anom_pred & ~is_anom_true))
    fn = int(np.sum(~is_anom_pred & is_anom_true))
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    metrics = {
        "note": "Evaluated on a held-out split, ONLY against synthetic INJECTED outliers "
                "(is_anomaly_injected) — not real fraud/anomaly labels. Unsupervised models "
                "have no real ground truth here; this is a sanity check, not a real-world claim.",
        "injected_anomaly_count": int(is_anom_true.sum()),
        "flagged_count": int(is_anom_pred.sum()),
        "precision_vs_injected": round(precision, 4),
        "recall_vs_injected": round(recall, 4),
        "f1_vs_injected": round(f1, 4),
    }
    print(f"  flagged={metrics['flagged_count']} injected={metrics['injected_anomaly_count']} "
          f"precision={metrics['precision_vs_injected']} recall={metrics['recall_vs_injected']}")

    metadata = ModelMetadata(
        model_name="anomaly", version=VERSION, training_timestamp=now_iso(),
        dataset_type=DATASET_TYPE_SYNTHETIC, feature_version=FEATURE_VERSION,
        algorithm="IsolationForest", training_sample_count=len(train_idx), validation_sample_count=len(test_idx),
        metrics=metrics, status=STATUS_EXPERIMENTAL, real_sample_count=0,
        notes="Unsupervised — advisory only, never blocks a financial action. Real-world precision/recall unknown.",
    )
    path = ModelRegistry.path_for("anomaly", VERSION)
    model.save(path)
    (path / "metadata.json").write_text(__import__("json").dumps(metadata.to_dict(), indent=2))
    print(f"  saved -> ai/artifacts/anomaly/{VERSION}")
    return metadata


def train_channel_and_response(case_df: pd.DataFrame, real_comm_n: int):
    _print_header("MODELS 8 & 9 — Communication Channel + Message Response")
    comm_df = generate_communication_trials(case_df)
    feats_cols = ["channel", "message_type", "prior_communications_24h"]
    feats = pd.DataFrame([
        {**build_case_features(r, failure_category=r["failure_category"]),
         "channel": r["channel"], "message_type": r["message_type"],
         "prior_communications_24h": r["prior_communications_24h"]}
        for r in comm_df.to_dict("records")
    ])
    y = comm_df["responded"].values
    X_train, X_test, y_train, y_test = train_test_split(feats, y, test_size=0.2, random_state=SEED, stratify=y)

    results = {}
    for mod, name, status in [
        (channel_model, "communication_channel", STATUS_READY),
        (response_model, "message_response", STATUS_DATA_LIMITED),
    ]:
        model = TabularModel(mod.build_estimator(), mod.NUMERIC_FEATURES, mod.CATEGORICAL_FEATURES, task="classification")
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        proba = model.predict_proba(X_test)[:, list(model.classes_).index(True)]
        metrics = _classification_metrics(y_test, y_pred, y_proba=proba, positive_label=True)
        print(f"  [{name}] accuracy={metrics['accuracy']} roc_auc={metrics.get('roc_auc')}")

        metadata = ModelMetadata(
            model_name=name, version=VERSION, training_timestamp=now_iso(),
            dataset_type=DATASET_TYPE_SYNTHETIC, feature_version=FEATURE_VERSION,
            algorithm=type(model.pipeline.named_steps["model"]).__name__,
            training_sample_count=len(X_train), validation_sample_count=len(X_test),
            metrics=metrics, status=status, label_classes=[False, True], real_sample_count=real_comm_n,
            notes=f"Real recon_dev.db communications rows found: {real_comm_n} — far below any usable "
                  f"training threshold; trained entirely on synthetic engagement assumptions."
                  + ("" if status != STATUS_DATA_LIMITED else " Marked DATA_LIMITED per Phase 6 directive."),
        )
        ModelRegistry.save(name, VERSION, model, metadata)
        print(f"  saved -> ai/artifacts/{name}/{VERSION}")
        results[name] = metadata
    return results


def train_strategy_ranking(case_df: pd.DataFrame):
    _print_header("MODEL 6 — Recovery Strategy Ranking")
    trials = generate_strategy_trials(case_df)
    feats = pd.DataFrame([
        {**build_case_features(r, failure_category=r["failure_category"]), "strategy": r["strategy"]}
        for r in trials.to_dict("records")
    ])
    y = trials["strategy_recovered"].values
    X_train, X_test, y_train, y_test = train_test_split(feats, y, test_size=0.2, random_state=SEED, stratify=y)

    model = TabularModel(strategy_ranking_model.build_estimator(), strategy_ranking_model.NUMERIC_FEATURES,
                         strategy_ranking_model.CATEGORICAL_FEATURES, task="classification")
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    proba = model.predict_proba(X_test)[:, list(model.classes_).index(True)]
    metrics = _classification_metrics(y_test, y_pred, y_proba=proba, positive_label=True)
    print(f"  accuracy={metrics['accuracy']} roc_auc={metrics.get('roc_auc')} (n_trials={len(trials)})")

    metadata = ModelMetadata(
        model_name=strategy_ranking_model.MODEL_NAME, version=VERSION, training_timestamp=now_iso(),
        dataset_type=DATASET_TYPE_SYNTHETIC, feature_version=FEATURE_VERSION,
        algorithm=type(model.pipeline.named_steps["model"]).__name__,
        training_sample_count=len(X_train), validation_sample_count=len(X_test),
        metrics=metrics, status=STATUS_READY, label_classes=[False, True], real_sample_count=0,
        notes="Trained on counterfactual (case, candidate strategy) synthetic trials; ranking at "
              "inference scores every real StrategyAction candidate with this one model.",
    )
    ModelRegistry.save(strategy_ranking_model.MODEL_NAME, VERSION, model, metadata)
    print(f"  saved -> ai/artifacts/{strategy_ranking_model.MODEL_NAME}/{VERSION}")
    return metadata


def main() -> int:
    print("RECON OS — Phase 6 ML Training Pipeline")
    print(f"Feature version: {FEATURE_VERSION}  |  Model version: {VERSION}  |  Seed: {SEED}")

    # --- Real data: honestly reported, not used for training (insufficient) ---
    _print_header("REAL DATA (recon_dev.db)")
    try:
        import database
        database.init_db()   # ensures lightweight migrations (e.g. ml_predictions_json) have run
        db = database.SessionLocal()
        try:
            real_case_df = extract_real_case_dataset(db)
            from models.communication import Communication
            real_comm_n = db.query(Communication).count()
        finally:
            db.close()
    except Exception as e:
        print(f"  Could not read recon_dev.db ({e}) — proceeding with synthetic data only.")
        real_case_df = pd.DataFrame()
        real_comm_n = 0
    _report_real_data(real_case_df)
    real_n = len(real_case_df)

    # --- Synthetic dataset: the actual training source (clearly labeled) ---
    _print_header("SYNTHETIC DATASET (DEVELOPMENT/VALIDATION — NOT real customer data)")
    case_df = generate_case_dataset(n=3000, seed=SEED)
    print(f"Generated {len(case_df)} synthetic cases | recovered={int(case_df['recovered'].sum())} "
          f"({case_df['recovered'].mean():.1%}) | categories={sorted(case_df['failure_category'].unique())}")

    results = {}
    results["diagnosis"] = train_diagnosis(case_df, real_n)
    results["recovery_probability"] = train_recovery_probability(case_df, real_n)
    results["strategy_ranking"] = train_strategy_ranking(case_df)
    comm_results = train_channel_and_response(case_df, real_comm_n)
    results.update(comm_results)
    results["recovery_time"] = train_recovery_time(case_df, real_n)
    results["customer_recovery"] = train_customer_recovery(case_df, real_n)
    results["anomaly"] = train_anomaly(case_df)

    _print_header("SUMMARY")
    for name, meta in results.items():
        if meta is None:
            print(f"  {name:24s} SKIPPED (insufficient data)")
        else:
            key_metric = next(iter(meta.metrics.items())) if meta.metrics else ("-", "-")
            print(f"  {name:24s} status={meta.status:12s} n_train={meta.training_sample_count:5d} "
                 f"n_val={meta.validation_sample_count:5d}  {key_metric[0]}={key_metric[1]}")

    print("\nAll artifacts written under apps/api/ai/artifacts/ (gitignored — rerun this command to regenerate).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
