# Copyright (c) 2026 Elee Beaulieu. All rights reserved.

"""Script de consolidation du Grand Livre allégé sans statement_date."""

import logging
from pathlib import Path
import re
import sys

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_LEDGER = DATA_DIR / "all_transactions.csv"


def clean_section_label(val: str) -> str:
    """Normalise les libellés de sous-comptes."""
    if not isinstance(val, str):
        return "Autre"
    val = re.sub(r"\(No de contrat\s*:\s*[^\)]+\)", "", val).strip()
    if "PROFIT JEUNESSE" in val.upper():
        return "Desjardins - Compte Profit Jeunesse"
    if "OPÉRATIONS COURANTES" in val.upper():
        return "Desjardins - Opérations Courantes"
    if "CELI" in val.upper():
        return "Desjardins - Épargne CELI"
    if "COMPTE D'EPARGNE" in val.upper() or "ÉPARGNE" in val.upper():
        return "Desjardins - Épargne & Placements"
    if "PRÊT" in val.upper() or "PRET" in val.upper() or "PR " in val.upper():
        return "Desjardins - Prêt Étudiant"
    if "COSTCO" in val.upper():
        return "CIBC - Costco Mastercard"
    if "MASTERCARD" in val.upper() or "VISA" in val.upper():
        return "Desjardins - Carte de Crédit"
    return val


def main():
    """Consolide les sources en un schéma clair et unifié."""
    source_files = [
        DATA_DIR / "desjardins_debit_transactions.csv",
        DATA_DIR / "desjardins_transactions.csv",
        DATA_DIR / "cibc_transactions.csv",
    ]

    dfs = []
    for f in source_files:
        if f.exists():
            df_src = pd.read_csv(f)
            logger.info("Chargement : %s (%s lignes)", f.name, f"{len(df_src):,}")
            dfs.append(df_src)

    if not dfs:
        logger.error("[!] Aucun fichier source trouvé dans %s", DATA_DIR)
        sys.exit(1)

    master_df = pd.concat(dfs, ignore_index=True)

    if "date" not in master_df.columns or master_df["date"].isna().any():
        master_df["date"] = master_df["date"].fillna(master_df.get("transaction_date"))

    master_df["account_section"] = master_df["account_section"].apply(clean_section_label)
    master_df = master_df.dropna(subset=["amount"])
    master_df = master_df.sort_values(by="date", ascending=False).reset_index(drop=True)

    ordered_cols = [
        "date",
        "transaction_date",
        "posting_date",
        "institution",
        "account_type",
        "account_section",
        "code",
        "remise",
        "raw_category",
        "description",
        "amount",
        "source_file",
    ]
    existing_cols = [c for c in ordered_cols if c in master_df.columns]
    master_df = master_df[existing_cols]

    master_df.to_csv(OUTPUT_LEDGER, index=False, encoding="utf-8")
    logger.info("\n[✓] Grand livre unifié généré : %s", OUTPUT_LEDGER)
    logger.info("    Total de transactions : %s", f"{len(master_df):,}")


if __name__ == "__main__":
    main()
