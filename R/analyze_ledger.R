# ==============================================================================
# Analyse financière - Grand livre unifié
# Stack: R (tidyverse, lubridate, scales)
# ==============================================================================

suppressPackageStartupMessages({
  library(readr)
  library(dplyr)
  library(tidyr)
  library(lubridate)
  library(stringr)
  library(ggplot2)
  library(scales)
  library(forcats)
})

# Détection robuste du chemin du fichier
repo_dir <- "C:/Users/sport/Downloads/monopoly-repo"
csv_file <- file.path(repo_dir, "all_transactions.csv")

if (!file.exists(csv_file)) {
  stop("Fichier introuvable : ", csv_file, ". Exécutez d'abord merge_master_ledger.py")
}

# 1. Importation et typage des données
df <- read_csv(
  csv_file,
  col_types = cols(
    date = col_date(format = "%Y-%m-%d"),
    institution = col_character(),
    account_type = col_character(),
    account_section = col_character(),
    description = col_character(),
    amount = col_double(),
    code = col_character(),
    statement_date = col_date(format = "%Y-%m-%d"),
    source_file = col_character()
  ),
  show_col_types = FALSE
) %>%
  mutate(
    institution = as_factor(institution),
    account_type = as_factor(account_type),
    year = year(date),
    month_date = floor_date(date, unit = "month"),
    flow_type = if_else(amount < 0, "Sortie (Dépense)", "Entrée (Revenu/Dépôt)")
  )

cat("\n============================================================\n")
cat(sprintf("RÉSUMÉ DU GRAND LIVRE : %s transactions chargées\n", comma(nrow(df))))
cat(sprintf("Période : du %s au %s\n", min(df$date), max(df$date)))
cat("============================================================\n\n")

# 2. Résumé par Institution & Type de compte
cat("[1] Volume et soldes cumulés par type de compte :\n")
summary_accounts <- df %>%
  group_by(institution, account_type, account_section) %>%
  summarise(
    nb_tx = n(),
    total_sorties = sum(amount[amount < 0], na.rm = TRUE),
    total_entrees = sum(amount[amount > 0], na.rm = TRUE),
    solde_net = sum(amount, na.rm = TRUE),
    .groups = "drop"
  ) %>%
  arrange(institution, account_type, desc(nb_tx))

print(summary_accounts, n = 20)

# 3. Résumé mensuel des dépenses (Crédit + Débit)
cat("\n[2] Évolution mensuelle récente (derniers 12 mois) :\n")
monthly_summary <- df %>%
  group_by(month_date) %>%
  summarise(
    nb_tx = n(),
    total_depenses = abs(sum(amount[amount < 0], na.rm = TRUE)),
    total_entrees = sum(amount[amount > 0], na.rm = TRUE),
    flux_net = sum(amount, na.rm = TRUE),
    .groups = "drop"
  ) %>%
  arrange(desc(month_date))

print(head(monthly_summary, 12))

# 4. Génération du graphique
p <- ggplot(monthly_summary, aes(x = month_date)) +
  geom_col(aes(y = total_depenses), fill = "#d9534f", alpha = 0.8, width = 20) +
  geom_line(aes(y = total_entrees), color = "#2b8a3e", linewidth = 1) +
  geom_point(aes(y = total_entrees), color = "#2b8a3e", size = 2) +
  scale_y_continuous(labels = label_dollar(suffix = " $", prefix = "")) +
  scale_x_date(date_breaks = "6 months", date_labels = "%b %Y") +
  labs(
    title = "Évolution mensuelle des flux financiers",
    subtitle = "Colonnes rouges = Dépenses totales | Ligne verte = Entrées/Revenus",
    x = "Mois",
    y = "Montant ($ CAD)",
    caption = "Source: all_transactions.csv"
  ) +
  theme_minimal(base_size = 12) +
  theme(
    plot.title = element_text(face = "bold"),
    axis.text.x = element_text(angle = 45, hjust = 1)
  )

output_plot <- file.path(repo_dir, "monthly_flows.png")
ggsave(output_plot, plot = p, width = 10, height = 5, dpi = 300)
cat(sprintf("\n[✓] Graphique d'évolution mensuelle exporté : %s\n", output_plot))
