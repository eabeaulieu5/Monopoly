import sys
from datetime import date
from pathlib import Path

import pandas as pd

from monopoly.banks.desjardins import Desjardins
from monopoly.handler import StatementHandler
from monopoly.pdf import PdfDocument, PdfParser

OUTPUT_FILE = Path("desjardins_transactions.csv")


def get_target_directory() -> Path:
    while True:
        raw_input = input("Entrez le chemin du dossier contenant les PDF Desjardins (ou 'q' pour quitter) : ").strip()
        
        if raw_input.lower() in ("q", "quit", "exit"):
            print("Arrêt du script.")
            sys.exit(0)

        cleaned_path = raw_input.strip("\"'")
        target_dir = Path(cleaned_path).expanduser().resolve()

        if target_dir.is_dir():
            return target_dir
        
        print(f"[X] Dossier introuvable ou invalide : '{target_dir}'. Réessayez.\n")


def parse_tx_date(raw_date: str, stmt_date: date) -> date:
    """Transforme '19      07' en objet date ISO (YYYY-MM-DD)."""
    parts = raw_date.split()
    day, month = int(parts[0]), int(parts[1])
    year = stmt_date.year - 1 if month > stmt_date.month else stmt_date.year
    return date(year, month, day)


def parse_amount(val) -> float:
    """Ajuste le montant au format décimal standard en dollars."""
    return round(float(val) / 100.0, 2)


def main() -> None:
    releves_dir = get_target_directory()
    pdf_files = sorted(releves_dir.glob("*.pdf"))

    if not pdf_files:
        print(f"[!] Aucun fichier .pdf trouvé dans {releves_dir}")
        return

    print(f"\nDébut du traitement de {len(pdf_files)} fichiers Desjardins...")
    all_records = []

    for pdf_path in pdf_files:
        try:
            doc = PdfDocument(file_path=pdf_path)
            doc.unlock_document()

            parser = PdfParser(bank=Desjardins, document=doc)
            statement = StatementHandler(parser).statement
            stmt_date = statement.statement_date.date()

            if statement.transactions:
                for tx in statement.transactions:
                    all_records.append(
                        {
                            "date": parse_tx_date(tx.date, stmt_date),
                            "statement_date": stmt_date,
                            "description": tx.description.strip(),
                            "amount": parse_amount(tx.amount),
                            "source_file": pdf_path.name,
                        }
                    )
        except (RuntimeError, ValueError, OSError, TypeError) as err:
            print(f"[X] Erreur sur {pdf_path.name} : {err}")

    df = pd.DataFrame(all_records)

    if not df.empty:
        df.sort_values(by=["date", "statement_date"], inplace=True)
        df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")
        print(f"\n[✓] Succès : {len(df)} transactions exportées dans {OUTPUT_FILE}")
        print("\nAperçu des 10 premières lignes :")
        print(df.head(10).to_string(index=False))
    else:
        print("\n[!] Aucune transaction trouvée.")


if __name__ == "__main__":
    main()
