# Copyright (c) 2026 Elee Beaulieu. All rights reserved.

"""Script de consolidation du Grand Livre (Master Ledger) unifiant Débit/Crédit Desjardins et CIBC."""

import logging
from pathlib import Path
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_MASTER_CSV = DATA_DIR / "all_transactions.csv"

FILES = [
    DATA_DIR / "desjardins_debit_transactions.csv",
    DATA_DIR / "desjardins_transactions.csv",
    DATA_DIR / "cibc_transactions.csv",
]

def main():
    dfs = []
    for f in FILES:
        if f.exists():
            df_part = pd.read_csv(f)
            if "raw_category" in df_part.columns:
                df_part = df_part.drop(columns=["raw_category"])
            dfs.append(df_part)
            logger.info("Chargé : %s (%s lignes)", f.name, f"{len(df_part):,}")
        else:
            logger.warning("Fichier manquant : %s", f.name)

    if not dfs:
        logger.error("Aucun fichier source disponible pour la fusion.")
        return

    master_df = pd.concat(dfs, ignore_index=True)
    
    if "raw_category" in master_df.columns:
        master_df = master_df.drop(columns=["raw_category"])

    columns_order = [
        "date", "institution", "account_type", "account_section",
        "description", "category", "code", "amount", "statement_date", "source_file"
    ]
    for col in columns_order:
        if col not in master_df.columns:
            master_df[col] = None

    master_df = master_df[columns_order]
    
    master_df = master_df.drop_duplicates(subset=["date", "institution", "account_section", "description", "amount", "statement_date"])
    master_df = master_df.sort_values(by="date", ascending=False).reset_index(drop=True)
    
    master_df.to_csv(OUTPUT_MASTER_CSV, index=False, encoding="utf-8")
    logger.info("[✓] Grand Livre consolidé créé : %s (%s transactions)", OUTPUT_MASTER_CSV.name, f"{len(master_df):,}")

if __name__ == "__main__":
    main()
