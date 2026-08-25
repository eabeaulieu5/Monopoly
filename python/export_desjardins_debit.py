# Copyright (c) 2026 Elee Beaulieu. All rights reserved.

"""Extracteur Desjardins Débit avec validation stricte et clôture immédiate des transactions fermées."""

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

DATE_START_RE = re.compile(r"^\s*(\d{1,2}\s+[A-Za-zÉÉèéûû]{3,5}\.?)\s+(.*)$", re.IGNORECASE)

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
    "CIN", "CPP", "CRA", "CRS", "CSL", "COR", "REV", "MEQ", "CH"
}

ALL_KNOWN_CODES = set(BASE_DESJARDINS_CODES)
for c in list(BASE_DESJARDINS_CODES):
    ALL_KNOWN_CODES.add(f"I{c}")

SORTED_CODE_PATTERNS = sorted(ALL_KNOWN_CODES, key=len, reverse=True)


def parse_iso_date(raw_date: str, ref_year: int) -> str:
    parts = raw_date.strip().split()
    if len(parts) >= 2:
        d_str, m_str = parts[0], parts[1].lower().rstrip(".")
        m_num = MONTH_MAP.get(m_str, "01")
        return f"{ref_year:04d}-{m_num}-{int(d_str):02d}"
    return raw_date


def split_code_and_description(raw_body: str) -> tuple[str, str]:
    raw = raw_body.strip()
    for code in SORTED_CODE_PATTERNS:
        if raw.upper().startswith(code):
            remainder = raw[len(code):].strip()
            return code, remainder

    match = re.match(r"^([A-Za-z0-9]{1,4})\s+(.+)$", raw)
    if match:
        return match.group(1).upper(), match.group(2).strip()

    return "POS", raw


def determine_amount_sign(val: float, is_neg_token: bool, code_val: str, clean_desc: str, section: str) -> float:
    desc_upper = clean_desc.upper()
    if is_neg_token or code_val in {"CDT", "COR", "AJU"}:
        return abs(val)
    elif any(p in desc_upper for p in ["/ DE", " DE /", "REÇU", "RECU", "SALAIRE", "PAIE", "DÉPÔT", "DEPOT", "INTERET", "INTÉRÊT", "REMISE DE DETTE"]):
        return abs(val)
    elif any(p in desc_upper for p in ["/ À", "/ A", " À /", " A /", "ACHAT", "RETRAIT", "FRAIS", "PRELEVEMENT", "PRÉLÈVEMENT", "PAIEMENT"]):
        return -abs(val)
    elif code_val in {"DEP", "CT", "DDI", "SAL", "DIV", "DI", "CCN", "DVW", "INT", "IET", "ICP", "VAE", "VRW", "VIR", "IVIR", "MEQ"}:
        return abs(val)
    elif any(k in section.upper() for k in ["ÉPARGNE", "EPARGNE", "CELI"]):
        return abs(val)
    return -abs(val)


def extract_amounts_safe(tokens: list[str]) -> tuple[float | None, bool, list[str]]:
    """Isole le montant transactionnel et la description avec exactitude."""
    money_indices = []
    for i, t in enumerate(tokens):
        if "%" in t:
            continue
        t_clean = t.replace("$", "").replace("-", "")
        if re.match(r"^\d+[.,]\d{2}$", t_clean):
            money_indices.append(i)

    if not money_indices:
        return None, False, tokens

    if len(money_indices) >= 2:
        tx_idx = money_indices[-2]
    else:
        tx_idx = money_indices[-1]

    tx_tok = tokens[tx_idx].replace("$", "")
    is_neg = tx_tok.endswith("-") or tx_tok.startswith("-")
    clean_num = tx_tok.replace("-", "").replace(",", ".").replace(" ", "")

    try:
        base_val = float(clean_num)
    except ValueError:
        return None, False, tokens

    desc_tokens = tokens[:tx_idx]

    # Fusion des milliers sécurisée
    if desc_tokens:
        candidate_thousands = desc_tokens[-1]
        if re.match(r"^\d{1,2}$", candidate_thousands):
            prev_word = desc_tokens[-2] if len(desc_tokens) >= 2 else ""
            is_store_id = any(k in prev_word.upper() for k in ["#", "NO", "STORE", "MAGASIN", "W", "SUCC", "COMMERCE", "MARCHE", "ET", "EOP"]) or "#" in candidate_thousands
            int_part_len = len(clean_num.split(".")[0])
            if not is_store_id and int_part_len == 3 and base_val < 1000:
                thousands_val = int(candidate_thousands)
                base_val = (thousands_val * 1000.0) + base_val
                desc_tokens = desc_tokens[:-1]

    return base_val, is_neg, desc_tokens


def process_tx_block(block: dict, statement_date: str, ref_year: int, source_file: str) -> dict | None:
    full_text = " ".join(block["lines"]).strip()
    tokens = full_text.split()
    if not tokens:
        return None

    val, is_neg, desc_tokens = extract_amounts_safe(tokens)
    if val is None:
        return None

    raw_desc = " ".join(desc_tokens).strip()
    code_val, clean_desc = split_code_and_description(raw_desc)
    clean_desc = re.sub(r"[\$:]", "", clean_desc).strip()
    iso_date = parse_iso_date(block["raw_date"], ref_year)
    final_amt = determine_amount_sign(val, is_neg, code_val, clean_desc, block["section"])

    return {
        "date": iso_date,
        "institution": "Desjardins",
        "account_type": "Loan/Credit" if block["is_loan"] else "Debit/Banking",
        "account_section": block["section"],
        "description": clean_desc,
        "amount": final_amt,
        "code": code_val,
        "statement_date": statement_date,
        "source_file": source_file,
    }


def parse_desjardins_debit(pdf_path: Path) -> list[dict]:
    records = []
    current_section = "Compte Principal"
    statement_date = None
    ref_year = 2026
    is_loan_table = False

    file_match = re.search(r"(\d{4})(\d{2})(\d{2})\.pdf$", pdf_path.name)
    if file_match:
        y, m, d = file_match.groups()
        statement_date = f"{y}-{m}-{d}"
        ref_year = int(y)

    active_block = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                line_str = line.strip()
                if not line_str:
                    continue

                if not statement_date and "PÉRIODE DU" in line_str.upper():
                    hdr_match = re.search(r"au\s+(\d{1,2}\s+[A-Za-zÉÉèéûû]+\s+(\d{4}))", line_str, re.IGNORECASE)
                    if hdr_match:
                        statement_date = hdr_match.group(1)
                        ref_year = int(hdr_match.group(2))

                line_upper = line_str.upper()

                # 1. Filtre des lignes administratives et des soldes reportés / sommaires
                is_admin_line = any(k in line_upper for k in [
                    "SOLDE REPORTÉ", "SOLDE REPORTE", "SOLDE AU", "SOLDE PRÉCÉDENT", "SOLDE PRECEDENT",
                    "TOTAL DES", "TOTAL", "PAGE ", "DATE CODE DESCRIPTION", "PART DE QUALIFICATION"
                ])
                if is_admin_line:
                    if active_block:
                        rec = process_tx_block(active_block, statement_date, ref_year, pdf_path.name)
                        if rec:
                            records.append(rec)
                        active_block = None
                    continue

                # 2. Changement de section
                is_section_header = (
                    any(k in line_upper for k in ["COMPTE", "ÉPARGNE", "EPARGNE", "PRÊT", "PRET", "CELI", "MARGE", "PLACEMENT"])
                    and len(line_str) < 85
                    and not re.match(r"^\d{1,2}\s+[A-Za-zÉÉèéûû]{3,5}", line_str)
                )
                if is_section_header:
                    if active_block:
                        rec = process_tx_block(active_block, statement_date, ref_year, pdf_path.name)
                        if rec:
                            records.append(rec)
                        active_block = None

                    current_section = re.sub(r"\(SUITE\)", "", line_str, flags=re.IGNORECASE).strip()
                    is_loan_table = any(k in line_upper for k in ["PRÊT", "PRET", "MARGE", "PR "])
                    continue

                if "INTÉRÊT" in line_upper and "CAPITAL" in line_upper and "REMBOURSEMENT" in line_upper:
                    is_loan_table = True
                    continue
                elif "RETRAIT" in line_upper and "DÉPÔT" in line_upper and "SOLDE" in line_upper:
                    is_loan_table = False
                    continue

                # 3. Ligne débutant par une date
                tx_match = DATE_START_RE.match(line_str)
                if tx_match:
                    if active_block:
                        rec = process_tx_block(active_block, statement_date, ref_year, pdf_path.name)
                        if rec:
                            records.append(rec)

                    raw_date, rest_of_line = tx_match.groups()
                    active_block = {
                        "raw_date": raw_date.strip(),
                        "section": current_section,
                        "is_loan": is_loan_table,
                        "lines": [rest_of_line.strip()] if rest_of_line.strip() else []
                    }

                    # Si la ligne porte déjà au moins 2 montants (ex: 0.04 et 46.84), elle est complète
                    tokens_test = rest_of_line.split()
                    money_count = sum(1 for t in tokens_test if re.match(r"^\d+[.,]\d{2}$", t.replace("$", "").replace("-", "")))
                    if money_count >= 2:
                        rec = process_tx_block(active_block, statement_date, ref_year, pdf_path.name)
                        if rec:
                            records.append(rec)
                        active_block = None

                # 4. Continuation (uniquement si le bloc attend ses montants)
                elif active_block is not None:
                    active_block["lines"].append(line_str)

        if active_block:
            rec = process_tx_block(active_block, statement_date, ref_year, pdf_path.name)
            if rec:
                records.append(rec)

    return records


def main():
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
