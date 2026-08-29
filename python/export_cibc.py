import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pdfplumber

OUTPUT_FILE = Path("cibc_transactions.csv")

MONTH_MAP = {
    "jan": 1, "janv": 1, "janvier": 1,
    "fev": 2, "fév": 2, "février": 2,
    "mar": 3, "mars": 3,
    "avr": 4, "avril": 4,
    "mai": 5,
    "juin": 6,
    "juil": 7, "juillet": 7,
    "aout": 8, "août": 8,
    "sep": 9, "sept": 9, "septembre": 9,
    "oct": 10, "octobre": 10,
    "nov": 11, "novembre": 11,
    "dec": 12, "déc": 12, "décembre": 12,
}

TX_REGEX = re.compile(
    r"^(?:Ý\s*)?(?P<month>[a-zéû.-]+)\s+(?P<day>\d{1,2})\s+"
    r"[a-zéû.-]+\s+\d{1,2}\s+"
    r"(?P<description>.+?)\s+"
    r"(?P<amount>-?\d[\d\s]*[.,]\d{2})\s*$",
    re.IGNORECASE,
)

DATE_REGEX = re.compile(
    r"(?:Date du relevé\s*\n\s*|au\s+)(?P<day>\d{1,2})\s+(?P<month>[a-zéû.-]+)\s+(?P<year>\d{4})",
    re.IGNORECASE,
)


def get_target_directory() -> Path:
    while True:
        raw_input = input("Entrez le chemin du dossier contenant les PDF (ou 'q' pour quitter) : ").strip()
        
        if raw_input.lower() in ("q", "quit", "exit"):
            print("Arrêt du script.")
            sys.exit(0)

        cleaned_path = raw_input.strip("\"'")
        target_dir = Path(cleaned_path).expanduser().resolve()

        if target_dir.is_dir():
            return target_dir
        
        print(f"[X] Dossier introuvable ou invalide : '{target_dir}'. Réessayez.\n")


def parse_month(raw_month: str) -> int:
    clean = raw_month.strip().lower().rstrip(".")
    return MONTH_MAP.get(clean, 1)


def parse_amount(raw_amount: str) -> float:
    cleaned = raw_amount.replace(" ", "").replace(",", ".")
    val = float(cleaned)
    return -val


def main() -> None:
    releves_dir = get_target_directory()
    pdf_files = sorted(releves_dir.glob("*.pdf"))

    if not pdf_files:
        print(f"[!] Aucun fichier .pdf trouvé dans {releves_dir}")
        return

    print(f"\nDébut du traitement de {len(pdf_files)} fichiers CIBC...")
    all_records = []

    for pdf_path in pdf_files:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                full_text = "\n".join([page.extract_text() or "" for page in pdf.pages])

                # Extraction date du relevé
                stmt_date = None
                date_match = DATE_REGEX.search(full_text)
                if date_match:
                    d = int(date_match.group("day"))
                    m = parse_month(date_match.group("month"))
                    y = int(date_match.group("year"))
                    stmt_date = date(y, m, d)
                else:
                    fb = re.search(r"(\d{4})-(\d{2})-(\d{2})", pdf_path.name)
                    if fb:
                        stmt_date = date(int(fb.group(1)), int(fb.group(2)), int(fb.group(3)))

                if not stmt_date:
                    print(f"[X] Date introuvable sur {pdf_path.name}")
                    continue

                for page in pdf.pages:
                    text = page.extract_text()
                    if not text:
                        continue
                    for line in text.splitlines():
                        match = TX_REGEX.match(line.strip())
                        if match:
                            m_raw = match.group("month")
                            day = int(match.group("day"))
                            month = parse_month(m_raw)

                            year = stmt_date.year - 1 if month > stmt_date.month else stmt_date.year
                            tx_date = date(year, month, day)

                            desc = match.group("description").strip()
                            amount = parse_amount(match.group("amount"))

                            all_records.append(
                                {
                                    "date": tx_date,
                                    "statement_date": stmt_date,
                                    "description": desc,
                                    "amount": amount,
                                    "source_file": pdf_path.name,
                                }
                            )

        except Exception as err:
            print(f"[X] Erreur sur {pdf_path.name} : {err}")

    df = pd.DataFrame(all_records)

    if not df.empty:
        df.sort_values(by=["date", "statement_date"], inplace=True)
        df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")
        print(f"\n[✓] Succès : {len(df)} transactions CIBC exportées dans {OUTPUT_FILE}")
        print("\nAperçu des 10 premières lignes :")
        print(df.head(10).to_string(index=False))
    else:
        print("\n[!] Aucune transaction extraite.")


if __name__ == "__main__":
    main()
