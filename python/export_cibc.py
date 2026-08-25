# Copyright (c) 2026 Elee Beaulieu. All rights reserved.

"""Extracteur CIBC avec taxonomie officielle des catégories en français."""

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
SOURCE_DIR = REPO_ROOT.parent / "cibc_statements"

if not SOURCE_DIR.exists():
    SOURCE_DIR = REPO_ROOT / "cibc_statements"

MONTH_MAP = {
    "jan": "01", "janv": "01", "january": "01", "janvier": "01",
    "feb": "02", "fév": "02", "fev": "02", "february": "02", "février": "02",
    "mar": "03", "march": "03", "mars": "03",
    "apr": "04", "avr": "04", "april": "04", "avril": "04",
    "may": "05", "mai": "05",
    "jun": "06", "june": "06", "juin": "06",
    "jlt": "07", "jul": "07", "july": "07", "juil": "07", "juillet": "07",
    "aug": "08", "aoû": "08", "aou": "08", "august": "08", "août": "08",
    "sep": "09", "sept": "09", "september": "09", "septembre": "09",
    "oct": "10", "october": "10", "octobre": "10",
    "nov": "11", "november": "11", "novembre": "11",
    "dec": "12", "déc": "12", "december": "12", "décembre": "12",
}

# Taxonomie officielle CIBC (Français & Anglais)
CIBC_OFFICIAL_CATEGORIES = [
    # Catégories officielles complètes FR
    "Dépenses personnelles et dépenses du ménage",
    "Depenses personnelles et depenses du menage",
    "Services professionnels ou services financiers",
    "Magasins de détail et épicerie",
    "Magasins de detail et epicerie",
    "Rénovation de maison et de bureau",
    "Renovation de maison et de bureau",
    "Santé et éducation",
    "Sante et education",
    "Transports",
    "Transport",
    "Restaurants",
    "Restaurant",
    
    # Équivalents anglais et variantes raccourcies
    "Personal and Household Expenses",
    "Professional and Financial Services",
    "Retail and Grocery",
    "Home and Office Improvement",
    "Health and Education",
    "Transportation",
    "Recurring Payments",
    "Paiements récurrents",
    "Paiements recurrents",
    "Épicerie",
    "Epicerie",
    "Détail",
    "Detail",
    "Autre",
    "Other"
]

# Tri par longueur décroissante pour matcher les expressions les plus longues en premier
SORTED_CATEGORIES = sorted(CIBC_OFFICIAL_CATEGORIES, key=len, reverse=True)

TX_PATTERN_MONTH_FIRST = re.compile(
    r"^([A-Za-zÉÉèéûû]{3,9}\.?)\s+(\d{1,2})\s+(?:[A-Za-zÉÉèéûû]{3,9}\.?\s+)?(?:\d{1,2}\s+)?(.+?)\s+(-?\$?\s*\d{1,3}(?:[ ,]\d{3})*[.,]\d{2}-?)$",
    re.IGNORECASE
)

TX_PATTERN_DAY_FIRST = re.compile(
    r"^(\d{1,2})\s+([A-Za-zÉÉèéûû]{3,9}\.?)\s+(?:\d{1,2}\s+)?(?:[A-Za-zÉÉèéûû]{3,9}\.?\s+)?(.+?)\s+(-?\$?\s*\d{1,3}(?:[ ,]\d{3})*[.,]\d{2}-?)$",
    re.IGNORECASE
)

def parse_cibc_statement_date(pdf_path: Path) -> tuple[str, int, int]:
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", pdf_path.name)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{mo}-{d}", int(y), int(mo)
    return "2026-01-01", 2026, 1

def clean_and_split_desc_category(raw_desc: str) -> tuple[str, str]:
    """Nettoie le préfixe de date et sépare la description de la catégorie CIBC officielle."""
    desc = raw_desc.strip()
    
    # 1. Supprimer le résidu de posting date en tête
    desc = re.sub(
        r"^(?:[A-Za-zÉÉèéûû]{3,9}\.?\s+\d{1,2}|\d{1,2}\s+[A-Za-zÉÉèéûû]{3,9}\.?|\d{1,2})\s+",
        "",
        desc,
        flags=re.IGNORECASE
    ).strip()

    # 2. Si c'est un paiement, ne pas chercher de catégorie
    if any(k in desc.upper() for k in ["PAYMENT", "PAIEMENT"]):
        return desc, ""

    # 3. Extraction de la catégorie terminale officielle
    for cat in SORTED_CATEGORIES:
        pattern = rf"\s+{re.escape(cat)}$"
        if re.search(pattern, desc, re.IGNORECASE):
            clean_d = re.sub(pattern, "", desc, flags=re.IGNORECASE).strip()
            return clean_d, cat

    return desc, ""

def parse_cibc_pdf(pdf_path: Path) -> list[dict]:
    statement_date, ref_year, ref_month = parse_cibc_statement_date(pdf_path)
    records = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                line_str = line.strip()
                if not line_str or any(k in line_str.upper() for k in ["PAGE ", "PREVIOUS BALANCE", "SOLDE PRÉCÉDENT", "SUBTOTAL", "TOTAL", "CATÉGORIES DE DÉPENSES"]):
                    continue

                raw_month, raw_day, raw_desc, raw_amt = None, None, None, None

                m1 = TX_PATTERN_MONTH_FIRST.match(line_str)
                if m1:
                    m_tok, d_tok, raw_desc, raw_amt = m1.groups()
                    m_str = m_tok.lower().rstrip(".")
                    if m_str in MONTH_MAP:
                        raw_month = MONTH_MAP[m_str]
                        raw_day = int(d_tok)

                if not raw_month:
                    m2 = TX_PATTERN_DAY_FIRST.match(line_str)
                    if m2:
                        d_tok, m_tok, raw_desc, raw_amt = m2.groups()
                        m_str = m_tok.lower().rstrip(".")
                        if m_str in MONTH_MAP:
                            raw_month = MONTH_MAP[m_str]
                            raw_day = int(d_tok)

                if not raw_month or not raw_day or not raw_amt:
                    continue

                tx_month = int(raw_month)
                tx_year = ref_year - 1 if ref_month == 1 and tx_month == 12 else ref_year
                iso_date = f"{tx_year:04d}-{tx_month:02d}-{raw_day:02d}"

                merchant_desc, tx_cat = clean_and_split_desc_category(raw_desc)

                clean_amt_str = raw_amt.replace("$", "").replace(" ", "").replace(",", ".")
                is_credit = clean_amt_str.endswith("-") or clean_amt_str.startswith("-") or "PAYMENT" in merchant_desc.upper() or "PAIEMENT" in merchant_desc.upper()
                clean_amt_num = float(clean_amt_str.replace("-", ""))
                final_amt = clean_amt_num if is_credit else -clean_amt_num

                records.append({
                    "date": iso_date,
                    "institution": "CIBC",
                    "account_type": "Credit Card",
                    "account_section": "Credit Card Account",
                    "description": merchant_desc,
                    "category": tx_cat,
                    "amount": final_amt,
                    "statement_date": statement_date,
                    "source_file": pdf_path.name,
                })

    return records

def main():
    if not SOURCE_DIR.exists():
        logger.warning("[!] Dossier %s introuvable.", SOURCE_DIR)
        return

    pdf_files = sorted(list(SOURCE_DIR.glob("*.pdf")))
    all_records = []
    for pdf in pdf_files:
        recs = parse_cibc_pdf(pdf)
        all_records.extend(recs)

    df = pd.DataFrame(all_records)
    if not df.empty:
        df = df.sort_values(by="date", ascending=False).reset_index(drop=True)
        df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
        logger.info("[✓] %s transactions exportées dans %s", f"{len(df):,}", OUTPUT_CSV.name)
    else:
        logger.warning("[!] Aucune transaction extraite.")

if __name__ == "__main__":
    main()
