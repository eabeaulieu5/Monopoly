# Copyright (c) 2024 Benjamin AWD
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

from .base import BankBase  # Adjust relative path according to your structure
from .citibank import Citibank
from .dbs import Dbs
from .hsbc import Hsbc
from .maybank import Maybank
from .ocbc import Ocbc
from .standard_chartered import StandardChartered
from .trust import Trust
from .uob import Uob

__all__ = [
    "BankBase",
    "Citibank",
    "Dbs",
    "Hsbc",
    "Maybank",
    "Ocbc",
    "StandardChartered",
    "Trust",
    "Uob",
]
