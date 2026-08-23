import pandas as pd

df_desj = pd.read_csv("desjardins_transactions.csv")
df_desj["institution"] = "Desjardins"

df_cibc = pd.read_csv("cibc_transactions.csv")
df_cibc["institution"] = "CIBC"

df_all = pd.concat([df_desj, df_cibc], ignore_index=True)
df_all.sort_values(by=["date", "institution"], inplace=True)
df_all.to_csv("all_transactions.csv", index=False, encoding="utf-8")

print(f"[✓] Fusion terminée : {len(df_all)} transactions au total exportées dans all_transactions.csv")
