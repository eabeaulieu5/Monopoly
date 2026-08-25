# Copyright (c) 2026 Elee Beaulieu. All rights reserved.

"""Extracteur Crédit Desjardins (Visa) sans colonne code, avec dates ISO et attribution Visa."""

import logging
from pathlib import Path
import re
import sys
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_CSV = DATA_DIR / "desjardins_transactions.csv"

MONTH_NAME_MAP = {
    "january": "01", "janvier": "01", "jan": "01",
    "february": "02", "février": "02", "fevrier": "02", "feb": "02", "fev": "02",
    "march": "03", "mars": "03", "mar": "03",
    "april": "04", "avril": "04", "apr": "04", "avr": "04",
    "may": "05", "mai": "05",
    "june": "06", "juin": "06", "jun": "06",
    "july": "07", "juillet": "07", "jul": "07", "jlt": "07",
    "august": "08", "août": "08", "aout": "08", "aug": "08", "aoû": "08",
    "september": "09", "septembre": "09", "sep": "09", "sept": "09",
    "october": "10", "octobre": "10", "oct": "10",
    "november": "11", "novembre": "11", "nov": "11",
    "december": "12", "décembre": "12", "decembre": "12", "dec": "12", "déc": "12",
}

def parse_filename_metadata(filename: str) -> tuple[str, int, int]:
    m = re.search(r"^(\d{2})-.*?([A-Za-zÉÉèéûû]+)-(\d{4})\.pdf$", str(filename), re.IGNORECASE)
    if m:
        day_str, month_str, year_str = m.groups()
        month_num = MONTH_NAME_MAP.get(month_str.lower(), "01")
        iso_stmt = f"{year_str}-{month_num}-{day_str}"
        return iso_stmt, int(year_str), int(month_num)
    
    m_iso = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(filename))
    if m_iso:
        y, mo, d = m_iso.groups()
        return f"{y}-{mo}-{d}", int(y), int(mo)
        
    return "2026-01-01", 2026, 1

def fix_transaction_year(row: pd.Series) -> str:
    tx_date_str = str(row["date"])
    stmt_date_str = str(row["statement_date"])
    
    m_tx = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", tx_date_str)
    m_stmt = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", stmt_date_str)
    
    if m_tx and m_stmt:
        tx_y, tx_m, tx_d = m_tx.groups()
        stmt_y, stmt_m, _ = m_stmt.groups()
        if stmt_m == "01" and tx_m == "12" and tx_y == stmt_y:
            corrected_year = int(stmt_y) - 1
            return f"{corrected_year:04d}-{tx_m}-{tx_d}"
            
    return tx_date_str

def main():
    if not OUTPUT_CSV.exists():
        logger.warning("[!] Fichier %s introuvable.", OUTPUT_CSV)
        return

    df = pd.read_csv(OUTPUT_CSV)
    
    # Suppression de la colonne code
    if "code" in df.columns:
        df = df.drop(columns=["code"])
        
    # Normalisation Visa et compte
    df["institution"] = "Desjardins"
    df["account_type"] = "Credit Card"
    df["account_section"] = "Visa Account"
        
    # Normalisation statement_date
    if "source_file" in df.columns:
        parsed_metadata = df["source_file"].apply(parse_filename_metadata)
        df["statement_date"] = [m[0] for m in parsed_metadata]
        
    # Correction de passage d'année
    df["date"] = df.apply(fix_transaction_year, axis=1)

    ordered_cols = ["date", "institution", "account_type", "account_section", "description", "amount", "statement_date", "source_file"]
    existing_cols = [c for c in ordered_cols if c in df.columns]
    remaining = [c for c in df.columns if c not in existing_cols]
    df = df[existing_cols + remaining]
    
    df = df.sort_values(by="date", ascending=False).reset_index(drop=True)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
    logger.info("[✓] %s mis à jour avec le compte 'Visa Account' (%s lignes).", OUTPUT_CSV.name, f"{len(df):,}")

if __name__ == "__main__":
    main()
