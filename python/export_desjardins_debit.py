# Copyright (c) 2026 Elee Beaulieu. All rights reserved.

"""Extracteur de relevés bancaires de compte d'opérations courantes Desjardins."""

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
OUTPUT_CSV = DATA_DIR / "desjardins_debit_transactions.csv"

DATE_PATTERN = re.compile(r"^(\d{1,2}\s+[A-ZÉÛa-zéû]+\.?\s+\d{4})")


def parse_desjardins_debit(pdf_path: Path) -> list[dict]:
    """Extrait les transactions de débit et mouvements de sous-comptes."""
    records = []
    current_section = "Compte Principal"
    statement_date = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines = text.split("\n")

            for line in lines:
                if "EOP" in line or "COMPTE" in line or "ÉPARGNE" in line:
                    current_section = line.strip()

                if not statement_date and "Période du" in line:
                    stmt_match = re.search(r"au\s+(\d{1,2}\s+[A-ZÉÛa-zéû]+\.?\s+\d{4})", line)
                    if stmt_match:
                        statement_date = stmt_match.group(1)

                date_match = DATE_PATTERN.match(line)
                if date_match:
                    raw_date = date_match.group(1)
                    rem = line[len(raw_date):].strip()

                    # Détection code opération (3 lettres) + montant
                    code_match = re.search(r"\b([A-Z]{3})\b", rem)
                    code_val = code_match.group(1) if code_match else None

                    amt_matches = list(re.finditer(r"(-?[\d\s]+[.,]\d{2})\s*\$?$", rem))
                    if amt_matches:
                        last_amt = amt_matches[-1].group(1).replace(" ", "").replace(",", ".")
                        desc = rem[:amt_matches[-1].start()].strip()
                        try:
                            amt_val = float(last_amt)
                            records.append({
                                "date": raw_date,
                                "institution": "Desjardins",
                                "account_type": "Debit/Banking",
                                "account_section": current_section,
                                "description": desc,
                                "amount": amt_val,
                                "code": code_val,
                                "statement_date": statement_date,
                                "source_file": pdf_path.name,
                            })
                        except ValueError:
                            continue
    return records


def main():
    """Point d'entrée pour l'ingestion des relevés de débit Desjardins."""
    pdf_files = list(REPO_ROOT.glob("*.pdf")) + list((REPO_ROOT / "raw_pdf").glob("*.pdf"))
    all_records = []

    for pdf_file in pdf_files:
        if "815" in pdf_file.name or "debit" in pdf_file.name.lower():
            logger.info("Traitement : %s", pdf_file.name)
            all_records.extend(parse_desjardins_debit(pdf_file))

    if not all_records:
        logger.warning("[!] Aucune transaction de débit trouvée.")
        sys.exit(0)

    df = pd.DataFrame(all_records)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
    logger.info("[✓] %s transactions exportées dans %s", f"{len(df):,}", OUTPUT_CSV)


if __name__ == "__main__":
    main()
