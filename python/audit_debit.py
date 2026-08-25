# Copyright (c) 2026 Elee Beaulieu. All rights reserved.

"""Script d'audit et de validation des transactions de débit Desjardins."""

import logging
from pathlib import Path
import sys

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
CSV_PATH = DATA_DIR / "desjardins_debit_transactions.csv"

if not CSV_PATH.exists():
    CSV_PATH = REPO_ROOT / "desjardins_debit_transactions.csv"

if not CSV_PATH.exists():
    logger.error("[!] Fichier introuvable : %s", CSV_PATH)
    sys.exit(1)

df = pd.read_csv(CSV_PATH)

logger.info("=" * 60)
logger.info("AUDIT DESJARDINS DÉBIT : %s transactions", f"{len(df):,}")
logger.info("=" * 60)

null_amounts = df[df["amount"].isna()]
if not null_amounts.empty:
    logger.warning("[!] Montants manquants détectés : %d", len(null_amounts))
else:
    logger.info("[✓] Aucun montant manquant.")

logger.info("\n--- Répartition par sous-compte ---")
logger.info("%s", df["account_section"].value_counts().to_string())

total_depenses = df[df["amount"] < 0]["amount"].sum()
total_entrees = df[df["amount"] > 0]["amount"].sum()
logger.info("\n--- Flux totaux ---")
logger.info("Sorties : %s $", f"{total_depenses:,.2f}")
logger.info("Entrées : %s $", f"{total_entrees:,.2f}")
