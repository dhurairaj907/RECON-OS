"""RECON OS — Phase 6: dataset sources.

Two clearly-separated sources, never silently mixed:
    real_data.py       extracted from recon_dev.db (real customer/case rows)
    synthetic.py        deterministic, documented, explicitly labeled SYNTHETIC

Every row produced by either module carries a `dataset_type` column
("REAL" | "SYNTHETIC") that flows through to model metadata.
"""

DATASET_TYPE_REAL = "REAL"
DATASET_TYPE_SYNTHETIC = "SYNTHETIC"
