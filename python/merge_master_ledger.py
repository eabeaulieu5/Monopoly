import pandas as pd
from pathlib import Path

files = {
    "desjardins_credit": Path("desjardins_transactions.csv"),
    "cibc_credit": Path("cibc_transactions.csv"),
    "desjardins_debit": Path("desjardins_debit_transactions.csv")
}

dfs = []

# 1. Chargement Crédit Desjardins
if files["desjardins_credit"].exists():
    df_dc = pd.read_csv(files["desjardins_credit"])
    df_dc["institution"] = "Desjardins"
    df_dc["account_type"] = "Credit"
    if "account_section" not in df_dc.columns:
        df_dc["account_section"] = "Carte de crédit"
    dfs.append(df_dc)

# 2. Chargement Crédit CIBC
if files["cibc_credit"].exists():
    df_cc = pd.read_csv(files["cibc_credit"])
    df_cc["institution"] = "CIBC"
    df_cc["account_type"] = "Credit"
    if "account_section" not in df_cc.columns:
        df_cc["account_section"] = "Costco Mastercard"
    dfs.append(df_cc)

# 3. Chargement Débit Desjardins
if files["desjardins_debit"].exists():
    df_dd = pd.read_csv(files["desjardins_debit"])
    df_dd["institution"] = "Desjardins"
    df_dd["account_type"] = "Debit/Banking"
    dfs.append(df_dd)

if not dfs:
    print("[!] Aucun fichier CSV source trouvé.")
    exit()

# 4. Fusion et standardisation
df_all = pd.concat(dfs, ignore_index=True)

# Nettoyage des montants à 0.00 $ et conversion des dates
df_all = df_all[df_all["amount"] != 0.0].copy()
df_all["date"] = pd.to_datetime(df_all["date"])
df_all["statement_date"] = pd.to_datetime(df_all["statement_date"])

# Colonnes finales ordonnées
cols = [
    "date",
    "institution",
    "account_type",
    "account_section",
    "description",
    "amount",
    "code",
    "statement_date",
    "source_file"
]
for col in cols:
    if col not in df_all.columns:
        df_all[col] = None

df_all = df_all[cols].sort_values(by=["date", "institution", "account_type"], ascending=True)

output_path = Path("all_transactions.csv")
df_all.to_csv(output_path, index=False, encoding="utf-8")

print(f"[✓] Fichier unifié généré : {output_path.name}")
print(f"Total de transactions valides : {len(df_all)}")
print(f"Période couverte : du {df_all['date'].min().strftime('%Y-%m-%d')} au {df_all['date'].max().strftime('%Y-%m-%d')}")
