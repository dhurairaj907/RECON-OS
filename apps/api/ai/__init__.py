"""
RECON OS — Phase 6: Multi-Model AI Intelligence

Structure:
    ai/features/   centralized feature engineering (single source of truth)
    ai/data/       real-data extraction + clearly-labeled synthetic datasets
    ai/models/     trained model wrappers, one module per RECON model
    ai/training/   `python -m ai.training.train` — reproducible training pipeline
    ai/inference/  case -> features -> registry -> predictions (read-only, advisory)
    ai/artifacts/  generated model files (gitignored — rebuild via training)

SAFETY: every model here is advisory only. Nothing in this package writes to
RecoveryAction, calls the Razorpay adapter, sends a communication, or bypasses
the Policy Engine / human approval. See ai/inference/service.py.
"""
