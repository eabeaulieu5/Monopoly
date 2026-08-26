#!/usr/bin/env Rscript

# ==============================================================================
# Script : clean_cc_payments.R
# Description : Détection, audit et neutralisation des flux croisés de paiement
#               de cartes de crédit depuis le compte débit.
# ==============================================================================

suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
  library(stringr)
  library(lubridate)
})

# --- 1. Chemins d'accès ---
input_file <- "output/all_transactions.csv"
output_file <- "output/all_transactions_cleaned.csv"
audit_file <- "output/audit_matched_transfers.csv"

if (!file.exists(input_file)) {
  stop(paste("Fichier introuvable :", input_file))
}

# --- 2. Chargement et normalisation ---
df <- read_csv(input_file, show_col_types = FALSE) %>%
  mutate(
    date = as.Date(date),
    amount = as.numeric(amount),
    abs_amount = round(abs(amount), 2)
  )

if (!"id" %in% names(df)) {
  df <- df %>% mutate(row_id = row_number())
} else {
  df <- df %>% mutate(row_id = id)
}

# --- 3. Motifs de détection des virements / paiements ---
transfer_regex <- "PAIEMENT|PAYMENT|VIREMENT|VIR|TRANSFERT|PMT|MASTERCARD|VISA|DESJARDINS|CIBC"

debits <- df %>%
  filter(amount < 0, str_detect(description, regex(transfer_regex, ignore_case = TRUE)))

credits <- df %>%
  filter(amount > 0, str_detect(description, regex(transfer_regex, ignore_case = TRUE)))

# --- 4. Réconciliation (fenêtre de 0 à 4 jours ouvrables / week-end) ---
matched <- debits %>%
  inner_join(
    credits,
    by = "abs_amount",
    suffix = c("_debit", "_credit"),
    relationship = "many-to-many"
  ) %>%
  filter(
    date_credit >= date_debit,
    date_credit <= date_debit + days(4)
  )

matched_ids <- unique(c(matched$row_id_debit, matched$row_id_credit))

# --- 5. Marquage et filtrage ---
df_final <- df %>%
  mutate(
    is_internal_transfer = row_id %in% matched_ids | 
      (str_detect(description, regex(transfer_regex, ignore_case = TRUE)) & 
       (amount > 0 | amount < 0))
  )

df_cleaned <- df_final %>%
  filter(!is_internal_transfer) %>%
  select(-abs_amount, -is_internal_transfer)

# --- 6. Sauvegardes ---
if (!dir.exists("output")) {
  dir.create("output", recursive = TRUE)
}

write_csv(df_cleaned, output_file)
write_csv(matched, audit_file)

cat(sprintf("[✓] Nettoyage complété :\n"))
cat(sprintf("    - Transactions initiales : %d\n", nrow(df)))
cat(sprintf("    - Paires appariées neutralisées : %d\n", nrow(matched)))
cat(sprintf("    - Transactions finales conservées : %d\n", nrow(df_cleaned)))
cat(sprintf("    - Fichier nettoyé : %s\n", output_file))
cat(sprintf("    - Fichier d'audit : %s\n", audit_file))
