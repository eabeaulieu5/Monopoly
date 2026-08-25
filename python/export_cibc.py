# Copyright (c) 2026 Elee Beaulieu. All rights reserved.

"""Extracteur autonome de relevés CIBC avec description intégrale et catégorisation des remboursements."""

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

DATE_PATTERN = re.compile(
    r"^([A-Za-zÉÉèéûû]{3,4}\.?\s+\d{1,2}(?:\s+[A-Za-zÉÉèéûû]{3,4}\.?\s+\d{1,2})?)\s+",
    re.IGNORECASE,
)

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
    """Extrait la catégorie marchande sans modifier la description si c'est un paiement."""
    clean = text.strip()

    # Si paiement de facture / remboursement
    if "PAYMENT THANK YOU" in clean.upper() or "PAIEMENT MERCI" in clean.upper():
        return clean, "Paiement de solde / Remboursement"

    # Pour les achats marchands avec catégorie accolée à la fin
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


def parse_iso_date_cibc(raw_date_part: str, ref_year: int, stmt_date_str: str | None) -> str:
    """Convertit 'jan 02' en 'YYYY-MM-DD' avec gestion du saut d'année."""
    parts = raw_date_part.strip().split()
    if len(parts) >= 2:
        m_str, d_str = parts[0].lower().rstrip("."), parts[1]
        m_num = MONTH_MAP.get(m_str, "01")

        year = ref_year
        if stmt_date_str and "-01-" in stmt_date_str and m_num == "12":
            year -= 1

        return f"{year:04d}-{m_num}-{int(d_str):02d}"
    return raw_date_part


def parse_cibc(pdf_path: Path) -> list[dict]:
    """Extrait et normalise les transactions CIBC."""
    records = []
    statement_date = None
    ref_year = 2026

    file_match = re.search(r"(\d{4})-(\d{2})-(\d{2})\.pdf$", pdf_path.name)
    if file_match:
        statement_date = file_match.group(1)
        ref_year = int(file_match.group(1).split("-")[0])

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                line_str = line.strip()
                if not line_str:
                    continue

                if not statement_date and "Statement Date" in line_str:
                    stmt_match = re.search(r"Statement Date\s*:\s*([A-Za-z]+\s+\d{1,2},\s*(\d{4}))", line_str, re.IGNORECASE)
                    if stmt_match:
                        statement_date = stmt_match.group(1)
                        ref_year = int(stmt_match.group(2))

                if any(k in line_str.upper() for k in SUMMARY_KEYWORDS):
                    continue

                date_match = DATE_PATTERN.match(line_str)
                if not date_match:
                    continue

                full_date_block = date_match.group(1)
                rem = line_str[len(date_match.group(0)):].strip()

                date_parts = full_date_block.split()
                first_date = f"{date_parts[0]} {date_parts[1]}" if len(date_parts) >= 2 else full_date_block
                iso_date = parse_iso_date_cibc(first_date, ref_year, statement_date)

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
                        "date": iso_date,
                        "institution": "CIBC",
                        "account_type": "Credit",
                        "account_section": "Costco Mastercard",
                        "description": final_desc,
                        "raw_category": category,
                        "amount": final_amount,
                        "code": "PAYMENT" if is_credit else "PURCHASE",
                        "statement_date": statement_date,
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
    df = df.sort_values(by="date", ascending=False).reset_index(drop=True)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
    logger.info("[✓] %s transactions CIBC exportées dans %s", f"{len(df):,}", OUTPUT_CSV)


if __name__ == "__main__":
    main()
