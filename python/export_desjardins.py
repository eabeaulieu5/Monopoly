# Copyright (c) 2026 Elee Beaulieu. All rights reserved.

"""Extracteur de relevés PDF de cartes de crédit Desjardins."""

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
OUTPUT_CSV = DATA_DIR / "desjardins_transactions.csv"

DATE_PATTERN = re.compile(r"^(\d{1,2}\s+[A-ZÉÛa-zéû]+\.?\s+\d{4})")
AMOUNT_PATTERN = re.compile(r"(-?\d+[\s,]\d{2})\s*(\$)?$")


def parse_desjardins_credit(pdf_path: Path) -> list[dict]:
    """Extrait les transactions d'un relevé de carte de crédit Desjardins."""
    records = []
    statement_date = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines = text.split("\n")

            for line in lines:
                if not statement_date and "Période terminée le" in line:
                    match_stmt = re.search(r"(\d{1,2}\s+[A-ZÉÛa-zéû]+\.?\s+\d{4})", line)
                    if match_stmt:
                        statement_date = match_stmt.group(1)

                date_match = DATE_PATTERN.match(line)
                if date_match:
                    raw_date = date_match.group(1)
                    rem = line[len(raw_date):].strip()

                    # Détection montant à la fin
                    amt_match = re.search(r"(-?[\d\s]+[.,]\d{2})\s*\$?$", rem)
                    if amt_match:
                        raw_amt = amt_match.group(1).replace(" ", "").replace(",", ".")
                        desc = rem[:amt_match.start()].strip()
                        try:
                            amt_val = float(raw_amt)
                            # Sur relevé de crédit: un montant positif affiché est une dépense (débit sortant)
                            # On inverse pour harmoniser avec le standard (négatif = sortie)
                            records.append({
                                "date": raw_date,
                                "institution": "Desjardins",
                                "account_type": "Credit",
                                "account_section": "Mastercard/Visa",
                                "description": desc,
                                "amount": -amt_val if "CR" not in line else amt_val,
                                "code": None,
                                "statement_date": statement_date,
                                "source_file": pdf_path.name,
                            })
                        except ValueError:
                            continue
    return records


def main():
    """Point d'entrée pour l'ingestion des relevés de crédit Desjardins."""
    pdf_files = list(REPO_ROOT.glob("*.pdf")) + list((REPO_ROOT / "raw_pdf").glob("*.pdf"))
    all_records = []

    for pdf_file in pdf_files:
        if "815" not in pdf_file.name and "desjardins" in pdf_file.name.lower():
            logger.info("Traitement : %s", pdf_file.name)
            all_records.extend(parse_desjardins_credit(pdf_file))

    if not all_records:
        logger.warning("[!] Aucune transaction de crédit trouvée.")
        sys.exit(0)

    df = pd.DataFrame(all_records)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
    logger.info("[✓] %s transactions exportées dans %s", f"{len(df):,}", OUTPUT_CSV)


if __name__ == "__main__":
    main()
