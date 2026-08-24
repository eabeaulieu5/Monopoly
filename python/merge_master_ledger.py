# Copyright (c) 2026 Elee Beaulieu. All rights reserved.

"""Module de consolidation et d'harmonisation du Master Ledger bancaire."""

import logging
from pathlib import Path
import sys

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DATA_DIR = REPO_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

MASTER_OUTPUT = DATA_DIR / "all_transactions.csv"


def load_and_standardize() -> pd.DataFrame | None:
    """Charge, aligne les schémas et fusionne toutes les sources bancaires."""
    dfs: list[pd.DataFrame] = []

    sources = {
        "desjardins_credit": [
            DATA_DIR / "desjardins_transactions.csv",
            REPO_ROOT / "desjardins_transactions.csv",
        ],
        "cibc_credit": [
            DATA_DIR / "cibc_transactions.csv",
            REPO_ROOT / "cibc_transactions.csv",
        ],
        "desjardins_debit": [
            DATA_DIR / "desjardins_debit_transactions.csv",
            REPO_ROOT / "desjardins_debit_transactions.csv",
        ],
    }

    found_files: list[Path] = []
    for _name, paths in sources.items():
        for path in paths:
            if path.exists():
                found_files.append(path)
                break

    if not found_files:
        logger.error("[!] Aucun fichier source trouvé dans %s ou %s", DATA_DIR, REPO_ROOT)
        return None

    cols_required = [
        "date",
        "institution",
        "account_type",
        "account_section",
        "description",
        "amount",
    ]

    for file_path in found_files:
        logger.info("[+] Chargement de : %s", file_path.name)
        df = pd.read_csv(file_path)

        for col in cols_required:
            if col not in df.columns:
                df[col] = None

        if "code" not in df.columns:
            df["code"] = None
        if "statement_date" not in df.columns:
            df["statement_date"] = None
        if "source_file" not in df.columns:
            df["source_file"] = file_path.name

        dfs.append(df)

    master_df = pd.concat(dfs, ignore_index=True)
    master_df["date"] = pd.to_datetime(master_df["date"], errors="coerce")
    master_df = master_df.sort_values(by="date", ascending=False).reset_index(drop=True)

    master_df.to_csv(MASTER_OUTPUT, index=False, encoding="utf-8")
    logger.info("\n[✓] Grand livre unifié généré : %s", MASTER_OUTPUT)
    logger.info("    Total de transactions : %s", f"{len(master_df):,}")
    return master_df


if __name__ == "__main__":
    res = load_and_standardize()
    if res is None:
        sys.exit(1)
