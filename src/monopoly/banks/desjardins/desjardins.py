# Copyright (c) 2024 Benjamin AWD
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

import re
from typing import ClassVar

from monopoly.banks.base import BankBase
from monopoly.config import DateOrder, PdfConfig, StatementConfig
from monopoly.constants import EntryType
from monopoly.identifiers import IdentifierGroup, TextIdentifier


class Desjardins(BankBase):
    name = "desjardins"

    pdf_config: PdfConfig = PdfConfig(
        page_range=(0, None),
        remove_vertical_text=False,
    )

    identifiers: ClassVar[list[IdentifierGroup]] = [
        [
            TextIdentifier(text="Desjardins"),
        ]
    ]

    credit_statement: ClassVar[StatementConfig] = StatementConfig(
        statement_type=EntryType.CREDIT,
        header_pattern=re.compile(
            r"(?:Date de transaction\s+Date d'inscription|SOMMAIRE DES TRANSACTIONS COURANTES)"
        ),
        statement_date_pattern=re.compile(
            r"(?:Période couverte|Date du relevé|Date)\s*[:\s]*(?P<statement_date>\d{1,2}\s+[a-zéû.-]+\s+\d{4})",
            re.IGNORECASE,
        ),
        statement_date_order=DateOrder("DMY"),
        transaction_date_order=DateOrder("DMY"),
        transaction_pattern=re.compile(
            r"^\s*(?P<transaction_date>\d{2}\s+\d{2})\s+"
            r"\d{2}\s+\d{2}\s+"
            r"(?P<description>.+?)\s+"
            r"(?:(?:\d+[,.]\d{2}\s*%\s+)|\s+)"
            r"(?P<amount>\d[\d\s]*[.,]\d{2})(?P<polarity>CR)?\s*$",
            re.IGNORECASE,
        ),
        transaction_auto_polarity=True,
        safety_check=False,
        filename_fallback_pattern=re.compile(r"-([A-Za-z]+)-(\d{4})\.pdf$"),
    )

    statement_configs: ClassVar[list[StatementConfig]] = [credit_statement]
