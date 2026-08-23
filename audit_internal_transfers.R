# ==============================================================================
# Détection des transferts internes (Compte chèque <-> Cartes de crédit)
# Stack: R (tidyverse, lubridate, scales)
# ==============================================================================

suppressPackageStartupMessages({
  library(readr)
  library(dplyr)
  library(stringr)
  library(lubridate)
  library(scales)
})

repo_dir <- "C:/Users/sport/Downloads/monopoly-repo"
csv_file <- file.path(repo_dir, "all_transactions.csv")

if (!file.exists(csv_file)) {
  stop("Fichier introuvable : ", csv_file)
}

df <- read_csv(csv_file, show_col_types = FALSE) %>%
  mutate(
    date = as.Date(date),
    abs_amount = abs(amount)
  )

# 1. Isoler les paiements sortants du compte bancaire (Débit < 0)
# Motifs typiques : PAIEMENT ACCESD, PAIEMENT MASTERCARD, CIBC, VISA, etc.
debit_payments <- df %>%
  filter(
    account_type == "Debit/Banking",
    amount < 0,
    str_detect(str_to_upper(description), "PAIEM|ACCESD|MASTERCARD|VISA|CIBC|DESJARDINS")
  ) %>%
  select(
    debit_date = date,
    debit_account = account_section,
    debit_desc = description,
    debit_amount = amount,
    abs_amount
  )

# 2. Isoler les paiements entrants sur les cartes de crédit (Crédit > 0)
credit_payments <- df %>%
  filter(
    account_type == "Credit",
    amount > 0
  ) %>%
  select(
    credit_date = date,
    credit_institution = institution,
    credit_account = account_section,
    credit_desc = description,
    credit_amount = amount,
    abs_amount
  )

# 3. Jointure floue par montant identique et proximité de date (écart <= 4 jours)
matched_transfers <- inner_join(debit_payments, credit_payments, by = "abs_amount", relationship = "many-to-many") %>%
  mutate(day_diff = as.numeric(credit_date - debit_date)) %>%
  filter(abs(day_diff) <= 4) %>%
  arrange(desc(debit_date))

cat("\n======================================================================\n")
cat(sprintf("DÉTECTION DES TRANSFERTS INTERNES : %d correspondances trouvées\n", nrow(matched_transfers)))
cat(sprintf("Montant total réconcilié : %s\n", dollar(sum(matched_transfers$abs_amount))))
cat("======================================================================\n\n")

print(
  matched_transfers %>%
    select(
      debit_date,
      credit_date,
      day_diff,
      montant = abs_amount,
      carte_cible = credit_institution,
      debit_desc,
      credit_desc
    ) %>%
    head(25),
  n = 25
)

# 4. Sauvegarde du rapport d'audit des transferts
out_report <- file.path(repo_dir, "internal_transfers_audit.csv")
write_csv(matched_transfers, out_report)
cat(sprintf("\n[✓] Rapport exporté : %s\n", out_report))
