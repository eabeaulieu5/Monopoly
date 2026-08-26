# Copyright (c) 2026 Elee Beaulieu. All rights reserved.

"""Extracteur de débit Desjardins épuré sans statement_date."""

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
OUTPUT_CSV = DATA_DIR / "desjardins_debit_transactions.csv"

DATE_PATTERN = re.compile(r"^(\d{1,2}\s+[A-Za-zÉÉèéûû]{3,5}\.?)\s+", re.IGNORECASE)

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

BASE_DESJARDINS_CODES = {
    "ACH", "POS", "APA", "ART", "BNI", "CRM", "CRP", "PAI", "FAC", "TEL",
    "VMW", "VIW", "VIR", "VAE", "VME", "VAD", "VMD", "VMO", "VNW", "VRW", "VWW",
    "VAC", "VCA", "VDW", "VEW", "VF", "VFC", "VFF", "VFI", "VGA", "VGP", "VPA", "VTR", "VVD", "VBW", "VC", "VIP",
    "DEP", "CT", "DDI", "SAL", "DIV", "DCA", "DCC", "DCN", "DCP", "DCV", "CCN", "DVW", "DI",
    "RET", "DT", "RGA", "RGP", "AGA", "DAB", "GAB", "EDI",
    "PWW", "PPW", "PAC", "PCA", "PFN", "PFT", "RA", "PRV", "PRE", "RAV", "RAZ", "REC", "REM",
    "RIC", "RRC", "RS", "VER", "VAP", "XAC", "XGA", "XWW", "SCN",
    "INT", "IET", "ICP", "INP", "AOP", "ACS", "ADM", "AES", "AET", "FGD", "FAP", "FAD",
    "FCP", "FCR", "FDC", "FEQ", "FER", "FGA", "FGM", "FIR", "FIX", "FOV", "FPP", "FRP",
    "FSG", "FTC", "FTF", "FTX", "GWW", "GCW", "GTW", "COT", "RIF", "CR",
    "CHQ", "VIS", "AJU", "ANN", "CCT", "CDD", "CDI", "CDT", "CFG", "CFS", "CGA", "CHG",
    "CIN", "CPP", "CRA", "CRS", "CSL", "COR", "REV"
}

ALL_KNOWN_CODES = set(BASE_DESJARDINS_CODES)
for c in BASE_DESJARDINS_CODES:
    ALL_KNOWN_CODES.add(f"I{c}")

SORTED_CODE_PATTERNS = sorted(ALL_KNOWN_CODES, key=len, reverse=True)


def clean_section_name(raw_name: str) -> str:
    """Normalise les libellés de sous-comptes."""
    s = raw_name.replace("(SUITE)", "").replace("(suite)", "").strip()
    return re.sub(r"\s+", " ", s)


def split_code_and_description(raw_body: str) -> tuple[str, str]:
    """Extrait le code officiel Desjardins et la description marchande."""
    raw = raw_body.strip()
    for code in SORTED_CODE_PATTERNS:
        if raw.upper().startswith(code):
            remainder = raw[len(code):].strip()
            if len(code) == 2 and remainder and remainder[0].isalnum():
                continue
            return code, remainder

    match = re.match(r"^([A-Z]{2,4})\s+(.+)$", raw)
    if match:
        return match.group(1), match.group(2).strip()

    return "POS", raw


def parse_iso_date(raw_date: str, ref_year: int) -> str:
    """Convertit '31 DEC' ou '1 mai' en 'YYYY-MM-DD'."""
    parts = raw_date.strip().split()
    if len(parts) >= 2:
        d_str, m_str = parts[0], parts[1].lower().rstrip(".")
        m_num = MONTH_MAP.get(m_str, "01")
        return f"{ref_year:04d}-{m_num}-{int(d_str):02d}"
    return raw_date


def extract_amounts_and_clean_desc(tokens: list[str]) -> tuple[float | None, bool, str]:
    """Extrait le montant exact, gère le trailing minus et nettoie la description."""
    amt_indices = []
    has_trailing_minus_map = {}

    for i, tok in enumerate(tokens):
        tok_clean = tok.replace("$", "").strip()
        if re.match(r"^-?\d+[.,]\d{2}-?$", tok_clean):
            amt_indices.append(i)
            has_trailing_minus_map[i] = tok_clean.endswith("-") or tok_clean.startswith("-")

    if not amt_indices:
        return None, False, " ".join(tokens)

    if len(amt_indices) >= 2:
        tx_idx = amt_indices[-2]
    else:
        tx_idx = amt_indices[-1]

    is_neg_token = has_trailing_minus_map.get(tx_idx, False)
    raw_val_str = tokens[tx_idx].replace("$", "").replace("-", "").replace(",", ".").strip()

    try:
        base_val = float(raw_val_str)
    except ValueError:
        return None, False, " ".join(tokens)

    desc_tokens = tokens[:tx_idx]

    if desc_tokens:
        last_tok = desc_tokens[-1]
        if re.match(r"^\d{1,2}$", last_tok):
            prev_tok = desc_tokens[-2] if len(desc_tokens) >= 2 else ""
            if not any(k in prev_tok.upper() for k in ["#", "STORE", "MAGASIN", "W", "SUCC", "NO"]):
                thousands = int(last_tok)
                if base_val < 1000:
                    base_val = (thousands * 1000.0) + base_val
                    desc_tokens = desc_tokens[:-1]
        elif last_tok == "5" and base_val == 0.0:
            base_val = 500.00
            desc_tokens = desc_tokens[:-1]

    return base_val, is_neg_token, " ".join(desc_tokens)


def parse_desjardins_debit(pdf_path: Path) -> list[dict]:
    """Extrait et normalise les transactions d'un relevé de débit Desjardins."""
    records = []
    current_section = "Compte Principal"
    ref_year = 2026
    is_loan_table = False

    file_match = re.search(r"(\d{4})(\d{2})(\d{2})\.pdf$", pdf_path.name)
    if file_match:
        ref_year = int(file_match.group(1))

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                line_str = line.strip()
                if not line_str:
                    continue

                if "INTÉRÊT" in line_str.upper() and "CAPITAL" in line_str.upper() and "REMBOURSEMENT" in line_str.upper():
                    is_loan_table = True
                    continue
                elif "RETRAIT" in line_str.upper() and "DÉPÔT" in line_str.upper() and "SOLDE" in line_str.upper():
                    is_loan_table = False
                    continue

                if not DATE_PATTERN.match(line_str):
                    line_upper = line_str.upper()
                    if any(k in line_upper for k in ["COMPTE PROFIT JEUNESSE", "COMPTE D'OPÉRATIONS COURANTES", "COMPTE D'EPARGNE", "ÉPARGNE", "PRÊT", "PRET", "MARGE"]):
                        if len(line_str) < 80:
                            current_section = clean_section_name(line_str)
                            if any(k in line_upper for k in ["PRÊT", "PRET", "MARGE", "PR"]):
                                is_loan_table = True
                    continue

                date_match = DATE_PATTERN.match(line_str)
                raw_date = date_match.group(1)
                rem = line_str[len(date_match.group(0)):].strip()

                tokens = rem.split()
                if len(tokens) < 2:
                    continue

                amt_val, is_neg_token, raw_desc = extract_amounts_and_clean_desc(tokens)
                if amt_val is None:
                    continue

                code_val, clean_desc = split_code_and_description(raw_desc)
                clean_desc = re.sub(r"[\$:]", "", clean_desc).strip()
                iso_date = parse_iso_date(raw_date, ref_year)

                full_context = f"{code_val} {clean_desc}".upper()
                
                if code_val in {"CDT", "COR", "REM", "AJU"} or is_neg_token:
                    final_amount = abs(amt_val)
                else:
                    is_deposit = (
                        code_val in {"DEP", "CT", "DDI", "SAL", "DIV", "DI", "CCN", "DVW", "INT", "IET", "ICP", "VAE", "VRW", "IVMW", "IVIW", "IVIR"}
                        or any(k in full_context for k in ["DEPOT", "DÉPÔT", "PAIE", "SALAIRE", "INTERET", "INTÉRÊT", "VIREMENT / DE", "VIREMENT REÇU", "VIREMENT RECU"])
                    )

                    is_withdrawal = (
                        code_val in {"ACH", "POS", "APA", "ART", "PAI", "FAC", "TEL", "PWW", "PPW", "PAC", "RA", "PRV", "PRE", "RET", "DT", "RGA", "RGP", "AGA", "AOP", "FAP", "FGD", "FAD", "FCP", "CHQ"}
                        or any(k in full_context for k in ["ACHAT", "RETRAIT", "FRAIS", "VIREMENT / À", "VIREMENT / A", "PRELEVEMENT", "PRÉLÈVEMENT"])
                    )

                    if is_withdrawal and amt_val > 0:
                        final_amount = -amt_val
                    elif is_deposit and amt_val < 0:
                        final_amount = abs(amt_val)
                    else:
                        final_amount = amt_val

                records.append({
                    "date": iso_date,
                    "institution": "Desjardins",
                    "account_type": "Loan/Credit" if is_loan_table else "Debit/Banking",
                    "account_section": current_section,
                    "description": clean_desc,
                    "amount": final_amount,
                    "code": code_val,
                    "source_file": pdf_path.name,
                })
    return records


def main():
    """Point d'entrée pour l'ingestion des relevés de débit Desjardins."""
    source_dir = REPO_ROOT.parent / "desjardins_statements"
    pdf_files = sorted(list(source_dir.glob("*.pdf")))

    all_records = []
    for pdf_file in pdf_files:
        records = parse_desjardins_debit(pdf_file)
        all_records.extend(records)

    if not all_records:
        logger.warning("[!] Aucune transaction de débit trouvée.")
        sys.exit(0)

    df = pd.DataFrame(all_records)
    df = df.sort_values(by="date", ascending=False).reset_index(drop=True)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
    logger.info("[✓] %s transactions exportées dans %s", f"{len(df):,}", OUTPUT_CSV)


if __name__ == "__main__":
    main()
