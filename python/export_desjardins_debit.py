import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pdfplumber

OUTPUT_FILE = Path("desjardins_debit_transactions.csv")

MONTH_MAP = {
    "jan": 1, "janv": 1, "janvier": 1,
    "fev": 2, "fév": 2, "février": 2,
    "mar": 3, "mars": 3,
    "avr": 4, "avril": 4,
    "mai": 5,
    "jun": 6, "juin": 6, "jul": 7, "juil": 7, "juillet": 7,
    "aou": 8, "août": 8, "aout": 8,
    "sep": 9, "sept": 9, "septembre": 9,
    "oct": 10, "octobre": 10,
    "nov": 11, "novembre": 11,
    "dec": 12, "déc": 12, "décembre": 12,
}

PERIOD_REGEX = re.compile(
    r"au\s+(?P<day>\d{1,2})\s+(?P<month>[a-zéû.-]+)\s+(?P<year>\d{4})",
    re.IGNORECASE
)

DATE_CODE_PREFIX = re.compile(
    r"^(?P<day>\d{1,2})\s+(?P<month>[A-ZÉÛa-zéû]{3,4})\s+(?P<code>[A-Z0-9]{2,6})\s+"
)

ACCOUNT_HEADER_PREFIX = ("EOP ", "COMPTE ", "ET ", "CS ")


def get_target_directory() -> Path:
    while True:
        raw_input = input("Entrez le chemin du dossier contenant les PDF Débit Desjardins (ou 'q' pour quitter) : ").strip()

        if raw_input.lower() in ("q", "quit", "exit"):
            print("Arrêt du script.")
            sys.exit(0)

        cleaned_path = raw_input.strip("\"'")
        target_dir = Path(cleaned_path).expanduser().resolve()

        if target_dir.is_dir():
            return target_dir

        print(f"[X] Dossier introuvable ou invalide : '{target_dir}'. Réessayez.\n")


def clean_account_name(raw_name: str) -> str:
    cleaned = re.sub(r"\s*\(\s*SUITE\s*\)", "", raw_name, flags=re.IGNORECASE).strip()
    return cleaned


def parse_month(raw_month: str) -> int:
    clean = raw_month.strip().lower().rstrip(".")
    return MONTH_MAP.get(clean[:3], MONTH_MAP.get(clean, 1))


def parse_amount(text: str) -> float:
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ".").replace(" ", ""))
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def process_statement(pdf_path: Path):
    records = []
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join([p.extract_text() or "" for p in pdf.pages])
        p_match = PERIOD_REGEX.search(full_text)
        if not p_match:
            return records

        d = int(p_match.group("day"))
        m = parse_month(p_match.group("month"))
        y = int(p_match.group("year"))
        stmt_date = date(y, m, d)

        current_account = "COMPTE PRINCIPAL"

        for page in pdf.pages:
            words = page.extract_words(x_tolerance=3, y_tolerance=3)
            if not words:
                continue

            lines_dict = {}
            for w in words:
                top_key = round(w["top"] / 2.5) * 2.5
                lines_dict.setdefault(top_key, []).append(w)

            sorted_y = sorted(lines_dict.keys())
            for y_pos in sorted_y:
                line_words = sorted(lines_dict[y_pos], key=lambda x: x["x0"])
                line_text = " ".join([w["text"] for w in line_words]).strip()

                if any(line_text.startswith(prefix) for prefix in ACCOUNT_HEADER_PREFIX) and "Date Code" not in line_text:
                    current_account = clean_account_name(line_text)
                    continue

                m_prefix = DATE_CODE_PREFIX.match(line_text)
                if not m_prefix:
                    continue

                day = int(m_prefix.group("day"))
                month = parse_month(m_prefix.group("month"))
                year = stmt_date.year - 1 if month > stmt_date.month else stmt_date.year
                tx_date = date(year, month, day)
                code = m_prefix.group("code")

                desc_words = []
                retrait_val = None
                depot_val = None

                for w in line_words:
                    x = w["x0"]
                    txt = w["text"]
                    is_money = bool(re.match(r"^\d{1,3}(?:[ ,]\d{3})*\.\d{2}$", txt) or re.match(r"^\d+\.\d{2}$", txt))

                    if x < 390:
                        desc_words.append(txt)
                    elif 390 <= x < 480 and is_money:
                        retrait_val = parse_amount(txt)
                    elif 480 <= x < 540 and is_money:
                        depot_val = parse_amount(txt)

                desc_raw = " ".join(desc_words)
                desc_clean = DATE_CODE_PREFIX.sub("", desc_raw).strip()

                if retrait_val is not None:
                    final_amount = -retrait_val
                elif depot_val is not None:
                    final_amount = depot_val
                else:
                    continue

                records.append({
                    "date": tx_date,
                    "statement_date": stmt_date,
                    "account_section": current_account,
                    "code": code,
                    "description": desc_clean,
                    "amount": final_amount,
                    "source_file": pdf_path.name
                })
    return records


def main():
    releves_dir = get_target_directory()
    pdf_files = sorted(releves_dir.glob("*.pdf"))

    if not pdf_files:
        print(f"[!] Aucun fichier .pdf trouvé dans {releves_dir}")
        return

    print(f"\nTraitement et nettoyage des sous-comptes de {len(pdf_files)} fichiers Desjardins...")

    all_tx = []
    for f in pdf_files:
        try:
            txs = process_statement(f)
            all_tx.extend(txs)
        except Exception as e:
            print(f"[X] Erreur sur {f.name} : {e}")

    df = pd.DataFrame(all_tx)
    if not df.empty:
        df.sort_values(by=["date", "statement_date"], inplace=True)
        df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")
        print(f"\n[✓] Succès : {len(df)} transactions débit exportées dans {OUTPUT_FILE}")
        print("\nAperçu des 10 premières lignes :")
        print(df.head(10).to_string(index=False))
    else:
        print("\n[!] Aucune transaction détectée.")


if __name__ == "__main__":
    main()
