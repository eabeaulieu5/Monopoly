import pandas as pd
from pathlib import Path

FILE = Path("desjardins_debit_transactions.csv")

if not FILE.exists():
    print(f"[!] Fichier introuvable : {FILE}. Exécutez d'abord python export_desjardins_debit.py")
    exit()

df = pd.read_csv(FILE)
df["date"] = pd.to_datetime(df["date"])

print("=" * 60)
print(f"RAPPORT D'AUDIT : {len(df)} transactions débit détectées")
print(f"Période couverte : du {df['date'].min().strftime('%Y-%m-%d')} au {df['date'].max().strftime('%Y-%m-%d')}")
print("=" * 60)

# 1. Distribution par section de compte
print("\n[1] Répartition par sous-compte :")
account_summary = df.groupby("account_section").agg(
    total_tx=("amount", "count"),
    total_depenses=("amount", lambda x: x[x < 0].sum()),
    total_depots=("amount", lambda x: x[x > 0].sum()),
    net=("amount", "sum")
).reset_index()

for _, row in account_summary.iterrows():
    print(f" • {row['account_section'][:45]:<45} | {row['total_tx']:>4} tx | Sorties: {row['total_depenses']:>10.2f} $ | Entrées: {row['total_depots']:>10.2f} $")

# 2. Répartition par code d'opération
print("\n[2] Top 8 des types d'opérations (Codes) :")
top_codes = df["code"].value_counts().head(8)
for code, count in top_codes.items():
    print(f" • {code:<6} : {count:>4} transactions")

# 3. Vérification des anomalies / valeurs nulles
print("\n[3] Contrôle qualité des données :")
nulls = df.isnull().sum()
has_null = nulls.any()
if has_null:
    print(f" [!] Colonnes avec valeurs manquantes :\n{nulls[nulls > 0]}")
else:
    print(" [✓] Aucune valeur manquante (NaN) détectée.")

zero_amounts = df[df["amount"] == 0]
if len(zero_amounts) > 0:
    print(f" [!] {len(zero_amounts)} transaction(s) avec un montant de 0.00 $ trouvée(s).")
else:
    print(" [✓] Tous les montants extraits sont non nuls.")

print("=" * 60)
