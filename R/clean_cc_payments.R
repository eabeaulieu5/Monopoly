#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
  library(stringr)
  library(lubridate)
})

input_file  <- "data/all_transactions.csv"
output_file <- "data/all_transactions_cleaned.csv"
audit_file  <- "data/audit_matched_transfers.csv"

# 1. Chargement et typage
df <- read_csv(input_file, show_col_types = FALSE) %>%
  mutate(
    date             = as.Date(date),
    transaction_date = if ("transaction_date" %in% names(.)) as.Date(transaction_date) else as.Date(NA),
    posting_date     = if ("posting_date" %in% names(.)) as.Date(posting_date) else as.Date(NA),
    amount           = as.numeric(amount),
    abs_amount       = round(abs(amount), 2),
    row_uid          = row_number()
  )

# 2. Motifs de détection
debit_pay_regex  <- "PAIEMENT FACTURE|PAIEMENT ACCESD|PAIEMENT CARTE|VIR.*CARTE|PAIEMENT.*CIBC|PAIEMENT.*DESJARDINS|PAIEMENT.*COSTCO"
credit_pay_regex <- "PAIEMENT MERCI|PAYMENT THANK YOU|PAIEMENT CAISSE|PAIEMENT ACCESD|PAIEMENT INTERNET|PAIEMENT DIRECT"

debit_payments <- df %>%
  filter(
    str_detect(account_type, regex("Debit|Banking", ignore_case = TRUE)),
    amount < 0,
    str_detect(description, regex(debit_pay_regex, ignore_case = TRUE))
  )

credit_payments <- df %>%
  filter(
    str_detect(account_type, regex("Credit", ignore_case = TRUE)),
    str_detect(description, regex(credit_pay_regex, ignore_case = TRUE)),
    !str_detect(description, regex("UNIVERSITE|SERV PMT", ignore_case = TRUE))
  )

# 3. Appariement avec fenêtre élargie à 10 jours
matched <- debit_payments %>%
  inner_join(
    credit_payments,
    by = "abs_amount",
    suffix = c("_debit_side", "_credit_side"),
    relationship = "many-to-many"
  ) %>%
  filter(
    date_credit_side >= date_debit_side - days(2),
    date_credit_side <= date_debit_side + days(10)
  )

matched_uids <- unique(c(matched$row_uid_debit_side, matched$row_uid_credit_side))

# 4. Suppression des paires + neutralisation résiduelle des remboursements de solde de cartes
df_cleaned <- df %>%
  mutate(
    is_cc_refund_orphan = str_detect(account_type, regex("Credit", ignore_case = TRUE)) & 
                          str_detect(description, regex(credit_pay_regex, ignore_case = TRUE)) &
                          !str_detect(description, regex("UNIVERSITE|SERV PMT", ignore_case = TRUE)),
    is_cc_debit_pay_orphan = str_detect(account_type, regex("Debit|Banking", ignore_case = TRUE)) & 
                             amount < 0 & 
                             str_detect(description, regex(debit_pay_regex, ignore_case = TRUE))
  ) %>%
  filter(!row_uid %in% matched_uids) %>%
  filter(!is_cc_refund_orphan) %>%
  filter(!is_cc_debit_pay_orphan) %>%
  select(-abs_amount, -row_uid, -is_cc_refund_orphan, -is_cc_debit_pay_orphan)

# 5. Exportation
write_csv(df_cleaned, output_file)
write_csv(matched, audit_file)

cat(sprintf("[✓] Nettoyage complet terminé :\n"))
cat(sprintf("    - Transactions initiales : %d\n", nrow(df)))
cat(sprintf("    - Paires appariées retirées : %d\n", nrow(matched)))
cat(sprintf("    - Transactions finales conservées : %d\n", nrow(df_cleaned)))
