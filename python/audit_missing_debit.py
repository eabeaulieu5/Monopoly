# Copyright (c) 2026 Elee Beaulieu. All rights reserved.

"""Audit de complétude calibré avec validation stricte des mois bancaires."""

from pathlib import Path
import re
import pandas as pd
import pdfplumber

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = REPO_ROOT.parent / "desjardins_statements"
CSV_PATH = REPO_ROOT / "data" / "desjardins_debit_transactions.csv"

df_extracted = pd.read_csv(CSV_PATH) if CSV_PATH.exists() else pd.DataFrame()

VALID_MONTHS = {
    "JAN", "JANV", "JANVIER", "FÉV", "FEV", "FÉVR", "FEVR", "FÉVRIER", "FEVRIER",
    "MAR", "MARS", "AVR", "AVRIL", "MAI", "JUN", "JUIN", "JLT", "JUIL", "JUILLET", "JUL",
    "AOÛ", "AOU", "AOÛT", "AOUT", "SEP", "SEPT", "SEPTEMBRE", "OCT", "OCTOBRE",
    "NOV", "NOVEMBRE", "DÉC", "DEC", "DÉCEMBRE", "DECEMBRE"
}

def is_real_tx_start(line: str) -> bool:
    m = re.match(r"^\s*(\d{1,2})\s+([A-Za-zÉÉèéûû]{3,9}\.?)\b", line)
    if not m:
        return False
    month_tok = m.group(2).upper().rstrip(".")
    return month_tok in VALID_MONTHS

print(f"{'Fichier PDF':<45} | {'Transactions PDF':>16} | {'CSV':>8} | {'Écart':>6}")
print("-" * 83)

total_pdf = 0
total_csv = len(df_extracted)

for pdf_file in sorted(list(SOURCE_DIR.glob("*.pdf"))):
    pdf_count = 0
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                l_str = line.strip()
                if any(k in l_str.upper() for k in ["TOTAL", "SOLDE AU", "SOLDE PRÉCÉDENT", "PÉRIODE DU", "PAGE "]):
                    continue
                if is_real_tx_start(l_str):
                    pdf_count += 1

    extracted_for_file = len(df_extracted[df_extracted["source_file"] == pdf_file.name]) if not df_extracted.empty else 0
    diff = pdf_count - extracted_for_file
    total_pdf += pdf_count

    if diff != 0:
        print(f"{pdf_file.name:<45} | {pdf_count:>16} | {extracted_for_file:>8} | {diff:>+6}")

print("-" * 83)
print(f"{'TOTAL GLOBAL':<45} | {total_pdf:>16} | {total_csv:>8} | {total_pdf - total_csv:>+6}")
