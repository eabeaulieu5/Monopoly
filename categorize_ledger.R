suppressPackageStartupMessages({
  library(readr)
  library(dplyr)
  library(stringr)
  library(ggplot2)
  library(scales)
  library(forcats)
  library(lubridate)
})

repo_dir <- "C:/Users/sport/Downloads/monopoly-repo"
csv_in <- file.path(repo_dir, "all_transactions.csv")
csv_out <- file.path(repo_dir, "all_transactions_categorized.csv")

if (!file.exists(csv_in)) {
  stop("Fichier introuvable : ", csv_in)
}

df <- read_csv(csv_in, show_col_types = FALSE)

categorize_transaction <- function(desc, account_sec, amt, code) {
  d <- str_to_upper(coalesce(desc, ""))
  s <- str_to_upper(coalesce(account_sec, ""))
  c <- str_to_upper(coalesce(code, ""))

  case_when(
    str_detect(d, "PAIEMENT|VIREMENT|VIR |VIW|VMW|PAIEM\\. INTERNET|ACCESD") |
      str_detect(c, "^(VIW|VMW|VRM|VAE)$") ~ "Transferts & Virements",

    str_detect(s, "CELI|EPARGNE|PLACEMENT|QUALIFICATION") |
      str_detect(d, "INTERET|INT\\.|IET") |
      str_detect(c, "^(IET|INT)$") ~ "Épargne & Placements",

    str_detect(d, "METRO|IGA|MAXI|PROVIGO|SUPER C|COSTCO WHOLESALE|WAL-MART|WALMART|MARCHE|EPICERIE") ~ "Épicerie",

    str_detect(d, "TIM HORTONS|STARBUCKS|VAN HOUTTE|MC DONALD|MCDONALD|SUBWAY|BOSTON PIZZA|A&W|REST|CAFE|BAR|PUB|PIZZA|SUSHI|BAKERY|BOULANGERIE|UBER EATS|DOORDASH") ~ "Restaurants & Sorties",

    str_detect(d, "PETRO|SHELL|ESSO|COUCHE-TARD|COUCHE TARD|HARNOIS|ULTRAMAR|HYDRO-QUEBEC|TRANSIT|RTC|STM|STLEVIS|TRAVERSIERS|PARKING|STATIONNEMENT|UBER TRIP|TAXI") ~ "Transport & Carburant",

    str_detect(d, "BELL|TELUS|VIDEOTRON|FIDO|KOODO|VIRGIN|HYDRO|ASSURANCE|DESJARDINS ASS") ~ "Factures & Services",

    str_detect(d, "JEAN COUTU|PHARMAPRIX|FAMILIPRIX|UNIPRIX|BRUNET|CLINIC|DENTIST|OPTIC") ~ "Santé & Pharmacie",

    str_detect(d, "SPOTIFY|NETFLIX|APPLE|GOOGLE|AMZN DIGITAL|PRIME|STEAM|PLAYSTATION|CINEMA|GYM|FITNESS") ~ "Loisirs & Abonnements",

    str_detect(d, "AMAZON|AMZN|WINNERS|MARSHALLS|OLD NAVY|H&M|SIMONS|DOLLARAMA|CANADIAN TIRE|BUREAU EN GROS") ~ "Achats & Magasinage",

    amt > 0 ~ "Revenus & Autres Entrées",

    TRUE ~ "Autres Dépenses"
  )
}

df_cat <- df %>%
  mutate(
    category = categorize_transaction(description, account_section, amount, code),
    category = as_factor(category),
    month_date = floor_date(as.Date(date), unit = "month")
  )

write_csv(df_cat, csv_out)
cat(sprintf("[✓] Grand livre catégorisé exporté : %s\n\n", csv_out))

cat("Distribution des dépenses par catégorie :\n")
cat_summary <- df_cat %>%
  filter(amount < 0, !category %in% c("Transferts & Virements", "Épargne & Placements")) %>%
  group_by(category) %>%
  summarise(
    nb_tx = n(),
    total = abs(sum(amount)),
    moyenne_tx = abs(mean(amount)),
    .groups = "drop"
  ) %>%
  mutate(pct = total / sum(total)) %>%
  arrange(desc(total))

print(cat_summary, n = 20)

p <- ggplot(cat_summary, aes(x = fct_reorder(category, total), y = total)) +
  geom_col(fill = "#2c7bb6", alpha = 0.85, width = 0.7) +
  coord_flip() +
  scale_y_continuous(labels = label_dollar(suffix = " $", prefix = "")) +
  labs(
    title = "Répartition cumulée des dépenses par catégorie",
    subtitle = "Exclut les transferts internes et virements d'épargne",
    x = NULL,
    y = "Total cumulé ($ CAD)"
  ) +
  theme_minimal(base_size = 11) +
  theme(plot.title = element_text(face = "bold"))

output_plot <- file.path(repo_dir, "expenses_by_category.png")
ggsave(output_plot, plot = p, width = 9, height = 5, dpi = 300)
cat(sprintf("\n[✓] Graphique exporté : %s\n", output_plot))
