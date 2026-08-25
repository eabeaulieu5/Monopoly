# Copyright (c) 2026 Elee Beaulieu. All rights reserved.

"""Extracteur autonome de relevés de crédit Desjardins avec dates ISO directes."""

import logging
from pathlib import Path
import re
import sys

import pandas as pd
import pdfplumber

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
OUTPUT_CSV = DATA_DIR / "desjardins_transactions.csv"

TX_PATTERN = re.compile(r"^(\d{2}\s+\d{2})\s+(\d{2}\s+\d{2})\s+(.+)$")


def parse_desjardins_credit(pdf_path: Path) -> list[dict]:
    """Extrait et normalise les transactions d'un relevé de carte de crédit Desjardins."""
    records = []
    statement_date = None
    ref_year = 2026

    file_match = re.search(r"([A-Za-z]+)-(\d{4})\.pdf$", pdf_path.name, re.IGNORECASE)
    if file_match:
        m_name, y = file_match.groups()
        statement_date = f"{m_name} {y}"
        ref_year = int(y)

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                line_str = line.strip()

                if not statement_date and "Période terminée le" in line_str:
                    match_stmt = re.search(r"(\d{1,2}\s+[A-Za-zÉÉèéûû]+\s+(\d{4}))", line_str, re.IGNORECASE)
                    if match_stmt:
                        statement_date = match_stmt.group(1)
                        ref_year = int(match_stmt.group(2))

                match = TX_PATTERN.match(line_str)
                if not match:
                    continue

                tx_date_raw = match.group(1)
                rem = match.group(3).strip()

                d_str, m_str = tx_date_raw.split()
                iso_date = f"{ref_year:04d}-{m_str}-{d_str}"

                amt_match = re.search(r"(-?[\d\s]+[.,]\d{2})\s*(CR)?$", rem, re.IGNORECASE)
                if amt_match:
                    raw_amt = amt_match.group(1).replace(" ", "").replace(",", ".")
                    is_credit = bool(amt_match.group(2))
                    desc = rem[:amt_match.start()].strip()
                    desc = re.sub(r"\s+\d+([.,]\d+)?\s*%\s*$", "", desc).strip()

                    try:
                        amt_val = float(raw_amt)
                        records.append({
                            "date": iso_date,
                            "institution": "Desjardins",
                            "account_type": "Credit",
                            "account_section": "Mastercard/Visa",
                            "description": desc,
                            "amount": amt_val if is_credit else -amt_val,
                            "code": "CR" if is_credit else "PURCHASE",
                            "statement_date": statement_date,
                            "source_file": pdf_path.name,
                        })
                    except ValueError:
                        continue
    return records


def main():
    """Point d'entrée pour l'ingestion des relevés de crédit Desjardins."""
    source_dir = REPO_ROOT.parent / "releves_extraits"
    pdf_files = sorted(list(source_dir.glob("*.pdf")))

    all_records = []
    for pdf_file in pdf_files:
        records = parse_desjardins_credit(pdf_file)
        all_records.extend(records)

    if not all_records:
        logger.warning("[!] Aucune transaction de crédit trouvée.")
        sys.exit(0)

    df = pd.DataFrame(all_records)
    df = df.sort_values(by="date", ascending=False).reset_index(drop=True)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
    logger.info("[✓] %s transactions exportées dans %s (dates ISO 100%%)", f"{len(df):,}", OUTPUT_CSV)


if __name__ == "__main__":
    main()
