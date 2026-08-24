# Copyright (c) 2026 Elee Beaulieu. All rights reserved.

"""Extracteur de relevés PDF de carte de crédit CIBC."""

import logging
from pathlib import Path
import re
import sys

import pdfplumber
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
OUTPUT_CSV = DATA_DIR / "cibc_transactions.csv"

DATE_PATTERN = re.compile(r"^([A-Z][a-z]{2}\s+\d{1,2})")


def parse_cibc(pdf_path: Path) -> list[dict]:
    """Extrait les transactions d'un relevé de carte CIBC."""
    records = []
    statement_date = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines = text.split("\n")

            for line in lines:
                if not statement_date and "Statement Date" in line:
                    stmt_match = re.search(r"Statement Date\s*:\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})", line)
                    if stmt_match:
                        statement_date = stmt_match.group(1)

                date_match = DATE_PATTERN.match(line)
                if date_match:
                    raw_date = date_match.group(1)
                    rem = line[len(raw_date):].strip()

                    amt_match = re.search(r"(-?[\d,]+\.\d{2})-?$", rem)
                    if amt_match:
                        raw_amt = amt_match.group(1).replace(",", "")
                        desc = rem[:amt_match.start()].strip()
                        try:
                            amt_val = float(raw_amt)
                            is_credit = line.strip().endswith("-") or "PAYMENT" in desc.upper()
                            records.append({
                                "date": raw_date,
                                "institution": "CIBC",
                                "account_type": "Credit",
                                "account_section": "Costco Mastercard",
                                "description": desc,
                                "amount": amt_val if is_credit else -amt_val,
                                "code": None,
                                "statement_date": statement_date,
                                "source_file": pdf_path.name,
                            })
                        except ValueError:
                            continue
    return records


def main():
    """Point d'entrée pour l'ingestion des relevés CIBC."""
    pdf_files = list(REPO_ROOT.glob("*.pdf")) + list((REPO_ROOT / "raw_pdf").glob("*.pdf"))
    all_records = []

    for pdf_file in pdf_files:
        if "cibc" in pdf_file.name.lower() or "costco" in pdf_file.name.lower():
            logger.info("Traitement : %s", pdf_file.name)
            all_records.extend(parse_cibc(pdf_file))

    if not all_records:
        logger.warning("[!] Aucune transaction CIBC trouvée.")
        sys.exit(0)

    df = pd.DataFrame(all_records)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
    logger.info("[✓] %s transactions exportées dans %s", f"{len(df):,}", OUTPUT_CSV)


if __name__ == "__main__":
    main()
