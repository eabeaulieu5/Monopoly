# Copyright (c) 2026 Elee Beaulieu. All rights reserved.

"""Extracteur de relevés de crédit CIBC épuré sans statement_date."""

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
OUTPUT_CSV = DATA_DIR / "cibc_transactions.csv"

DATE_PAIR_PATTERN = re.compile(
    r"^([A-Za-zÉÉèéûû]{3,4}\.?\s+\d{1,2})\s+([A-Za-zÉÉèéûû]{3,4}\.?\s+\d{1,2})\s+",
    re.IGNORECASE,
)
SINGLE_DATE_PATTERN = re.compile(
    r"^([A-Za-zÉÉèéûû]{3,4}\.?\s+\d{1,2})\s+",
    re.IGNORECASE,
)

MONTH_MAP = {
    "jan": "01", "janv": "01", "janvier": "01", "january": "01",
    "fév": "02", "fev": "02", "févr": "02", "fevr": "02", "février": "02", "fevrier": "02", "february": "02", "feb": "02",
    "mar": "03", "mars": "03", "march": "03",
    "avr": "04", "avril": "04", "april": "04", "apr": "04",
    "mai": "05", "may": "05",
    "jun": "06", "juin": "06", "june": "06",
    "jlt": "07", "juil": "07", "juillet": "07", "july": "07", "jul": "07",
    "aoû": "08", "aou": "08", "août": "08", "aout": "08", "august": "08", "aug": "08",
    "sep": "09", "sept": "09", "septembre": "09", "september": "09",
    "oct": "10", "octobre": "10", "october": "10",
    "nov": "11", "novembre": "11", "november": "11",
    "déc": "12", "dec": "12", "décembre": "12", "decembre": "12", "december": "12",
}

SUMMARY_KEYWORDS = [
    "TOTAL DES PAIEMENTS", "TOTAL DES NOUVEAUX PAIEMENTS", "TOTAL DES ACHATS",
    "TOTAL DES CRÉDITS", "TOTAL DES CREDITS", "SOLDE PRÉCÉDENT", "SOLDE PRECEDENT",
    "NOUVEAU SOLDE", "SOLDE EN COURS", "SOUS-TOTAL", "SUBTOTAL"
]

CIBC_CATEGORY_PATTERNS = [
    (re.compile(r"\s+(?:Voyages?\s+(?:et|/|\&)\s+transports?|Transports?\s+(?:et|/|\&)\s+voyages?|Transports?|Voyages?)$", re.IGNORECASE), "Transports et voyages"),
    (re.compile(r"\s+Magasins?\s+de\s+détail\s+et\s+épicerie[s]?$", re.IGNORECASE), "Magasins de détail et épicerie"),
    (re.compile(r"\s+Rénovation\s+de\s+maison\s+et\s+de\s+bureau$", re.IGNORECASE), "Rénovation de maison et de bureau"),
    (re.compile(r"\s+Services?\s+professionnels?\s+ou\s+services?$", re.IGNORECASE), "Services professionnels ou services"),
    (re.compile(r"\s+Services?\s+de\s+télécommunications?$", re.IGNORECASE), "Services de télécommunications"),
    (re.compile(r"\s+Station[s]?-service\s+et\s+essence$", re.IGNORECASE), "Station-service et essence"),
    (re.compile(r"\s+Santé\s+et\s+éducation$", re.IGNORECASE), "Santé et éducation"),
    (re.compile(r"\s+Hôtels,\s+divertissement\s+et\s+loisirs$", re.IGNORECASE), "Hôtels, divertissement et loisirs"),
    (re.compile(r"\s+Dépenses\s+personnelles\s+et\s+dépenses\s+du.*$", re.IGNORECASE), "Dépenses personnelles et ménage"),
    (re.compile(r"\s+Restaurants?$", re.IGNORECASE), "Restaurants"),
    (re.compile(r"\s+Divertissements?$", re.IGNORECASE), "Divertissement"),
    (re.compile(r"\s+Santé\s+et\s+soins\s+personnels?$", re.IGNORECASE), "Santé et soins personnels"),
    (re.compile(r"\s+Assurances?$", re.IGNORECASE), "Assurance"),
    (re.compile(r"\s+Frais\s+bancaires?$", re.IGNORECASE), "Frais bancaires"),
]


def extract_category_and_merchant(text: str) -> tuple[str, str | None]:
    """Extrait la catégorie marchande sans modifier la description si paiement."""
    clean = text.strip()
    if "PAYMENT THANK YOU" in clean.upper() or "PAIEMENT MERCI" in clean.upper():
        return clean, "Paiement de solde / Remboursement"

    for pattern, canonical_cat in CIBC_CATEGORY_PATTERNS:
        match = pattern.search(clean)
        if match:
            merchant = clean[:match.start()].strip()
            return merchant, canonical_cat

    return clean, None


def parse_canadian_amount(raw_str: str) -> float | None:
    """Convertit les montants québécois (virgule) et anglophones (point)."""
    s = raw_str.strip().replace("$", "").strip()
    if not s:
        return None

    is_neg = s.startswith("-") or s.endswith("-")
    s = s.strip("-").strip()

    if re.search(r",\d{2}$", s):
        s_clean = re.sub(r"[\s\.]", "", s[:-3]) + "." + s[-2:]
    elif re.search(r"\.\d{2}$", s):
        s_clean = re.sub(r"[\s\,]", "", s[:-3]) + "." + s[-2:]
    else:
        s_clean = re.sub(r"[\s\,\.]", "", s)

    try:
        val = float(s_clean)
        return -val if is_neg else val
    except ValueError:
        return None


def parse_iso_date_cibc(raw_date_part: str, ref_year: int, file_month: str) -> str:
    """Convertit 'jan 02' en 'YYYY-MM-DD' avec gestion du saut d'année."""
    parts = raw_date_part.strip().split()
    if len(parts) >= 2:
        m_str, d_str = parts[0].lower().rstrip("."), parts[1]
        m_num = MONTH_MAP.get(m_str, "01")

        year = ref_year
        if file_month == "01" and m_num == "12":
            year -= 1

        return f"{year:04d}-{m_num}-{int(d_str):02d}"
    return raw_date_part


def parse_cibc(pdf_path: Path) -> list[dict]:
    """Extrait et normalise les transactions CIBC."""
    records = []
    ref_year = 2026
    file_month = "01"

    file_match = re.search(r"(\d{4})-(\d{2})-(\d{2})\.pdf$", pdf_path.name)
    if file_match:
        ref_year = int(file_match.group(1))
        file_month = file_match.group(2)

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                line_str = line.strip()
                if not line_str:
                    continue

                if any(k in line_str.upper() for k in SUMMARY_KEYWORDS):
                    continue

                pair_match = DATE_PAIR_PATTERN.match(line_str)
                if pair_match:
                    raw_tx_date = pair_match.group(1)
                    raw_post_date = pair_match.group(2)
                    rem = line_str[len(pair_match.group(0)):].strip()
                else:
                    single_match = SINGLE_DATE_PATTERN.match(line_str)
                    if not single_match:
                        continue
                    raw_tx_date = single_match.group(1)
                    raw_post_date = single_match.group(1)
                    rem = line_str[len(single_match.group(0)):].strip()

                iso_tx_date = parse_iso_date_cibc(raw_tx_date, ref_year, file_month)
                iso_post_date = parse_iso_date_cibc(raw_post_date, ref_year, file_month)

                amt_match = re.search(r"(-?[\d\s\.,]+(?:,\d{2}|\.\d{2}))\s*\$?\s*(CR|-)?\s*\$?$", rem, re.IGNORECASE)
                if amt_match:
                    raw_amt_str = amt_match.group(1)
                    has_cr_or_minus = bool(amt_match.group(2)) or "-" in rem[amt_match.start():]
                    raw_desc = rem[:amt_match.start()].strip()

                    if any(k in raw_desc.upper() for k in SUMMARY_KEYWORDS):
                        continue

                    parsed_val = parse_canadian_amount(raw_amt_str)
                    if parsed_val is None:
                        continue

                    final_desc, category = extract_category_and_merchant(raw_desc)
                    is_credit = has_cr_or_minus or "PAYMENT" in raw_desc.upper() or "PAIEMENT" in raw_desc.upper()
                    final_amount = abs(parsed_val) if is_credit else -abs(parsed_val)

                    records.append({
                        "transaction_date": iso_tx_date,
                        "posting_date": iso_post_date,
                        "institution": "CIBC",
                        "account_type": "Credit",
                        "account_section": "CIBC - Costco Mastercard",
                        "description": final_desc,
                        "raw_category": category,
                        "amount": final_amount,
                        "source_file": pdf_path.name,
                    })
    return records


def main():
    """Point d'entrée pour l'ingestion des relevés CIBC."""
    source_dir = REPO_ROOT.parent / "CIBC_statements"
    pdf_files = sorted(list(source_dir.glob("*.pdf")))

    all_records = []
    for pdf_file in pdf_files:
        records = parse_cibc(pdf_file)
        all_records.extend(records)

    if not all_records:
        logger.warning("[!] Aucune transaction CIBC trouvée.")
        sys.exit(0)

    df = pd.DataFrame(all_records)
    df = df.sort_values(by="transaction_date", ascending=False).reset_index(drop=True)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
    logger.info("[✓] %s transactions CIBC exportées dans %s", f"{len(df):,}", OUTPUT_CSV)


if __name__ == "__main__":
    main()
