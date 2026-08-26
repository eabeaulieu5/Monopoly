# Copyright (c) 2026 Elee Beaulieu. All rights reserved.

"""Extracteur de relevés de crédit Desjardins épuré sans statement_date."""

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

MONTH_MAP = {
    "jan": "01", "janv": "01", "janvier": "01",
    "fév": "02", "fev": "02", "févr": "02", "fevr": "02", "février": "02", "fevrier": "02",
    "mar": "03", "mars": "03",
    "avr": "04", "avril": "04",
    "mai": "05",
    "jun": "06", "juin": "06",
    "jlt": "07", "juil": "07", "juillet": "07", "jul": "07",
    "aoû": "08", "aou": "08", "août": "08", "aout": "08",
    "sep": "09", "sept": "09", "septembre": "09",
    "oct": "10", "octobre": "10",
    "nov": "11", "novembre": "11",
    "déc": "12", "dec": "12", "décembre": "12", "decembre": "12",
}

TX_PATTERN = re.compile(r"^(\d{2}\s+\d{2})\s+(\d{2}\s+\d{2})\s+(.+)$")
END_LINE_PATTERN = re.compile(
    r"(?:(\d+(?:[.,]\d+)?\s*[%$])\s+)?(-?[\d\s]+[.,]\d{2})\s*(CR)?$",
    re.IGNORECASE,
)


def parse_desjardins_credit(pdf_path: Path) -> list[dict]:
    """Extrait les transactions de crédit Desjardins."""
    records = []
    ref_year = 2026
    file_month = "01"

    file_match = re.search(r"([A-Za-zÉÉèéûû]+)-(\d{4})\.pdf$", pdf_path.name, re.IGNORECASE)
    if file_match:
        m_name, y_str = file_match.groups()
        ref_year = int(y_str)
        file_month = MONTH_MAP.get(m_name.lower().rstrip("."), "01")

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                line_str = line.strip()
                if not line_str:
                    continue

                match = TX_PATTERN.match(line_str)
                if not match:
                    continue

                tx_date_raw = match.group(1)
                post_date_raw = match.group(2)
                rem = match.group(3).strip()

                d_tx, m_tx = tx_date_raw.split()
                d_post, m_post = post_date_raw.split()

                year_tx = ref_year
                year_post = ref_year

                if file_month == "01":
                    if m_tx == "12":
                        year_tx -= 1
                    if m_post == "12":
                        year_post -= 1

                iso_tx_date = f"{year_tx:04d}-{m_tx}-{d_tx}"
                iso_post_date = f"{year_post:04d}-{m_post}-{d_post}"

                end_match = END_LINE_PATTERN.search(rem)
                if end_match:
                    raw_remise = end_match.group(1)
                    raw_amt = end_match.group(2).replace(" ", "").replace(",", ".")
                    is_credit = bool(end_match.group(3))

                    desc = rem[:end_match.start()].strip()
                    remise_val = raw_remise.strip() if raw_remise else None

                    try:
                        amt_val = float(raw_amt)
                        is_payment = is_credit or "PAIEMENT" in desc.upper()
                        final_amt = abs(amt_val) if is_payment else -abs(amt_val)

                        records.append({
                            "transaction_date": iso_tx_date,
                            "posting_date": iso_post_date,
                            "institution": "Desjardins",
                            "account_type": "Credit",
                            "account_section": "Desjardins - Carte de Crédit",
                            "description": desc,
                            "remise": remise_val,
                            "amount": final_amt,
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
    df = df.sort_values(by="transaction_date", ascending=False).reset_index(drop=True)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
    logger.info("[✓] %s transactions exportées dans %s", f"{len(df):,}", OUTPUT_CSV)


if __name__ == "__main__":
    main()
