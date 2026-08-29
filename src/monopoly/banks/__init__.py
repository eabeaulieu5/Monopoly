# Copyright (c) 2024 Benjamin AWD
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

from .base import BankBase
from .citibank import Citibank
from .dbs import Dbs
from .detector import BankDetector
from .hsbc import Hsbc
from .maybank import Maybank
from .ocbc import Ocbc
from .standard_chartered import StandardChartered
from .trust import Trust
from .uob import Uob

banks = [
    Citibank,
    Dbs,
    Hsbc,
    Maybank,
    Ocbc,
    StandardChartered,
    Trust,
    Uob,
]

__all__ = [
    "BankBase",
    "BankDetector",
    "Citibank",
    "Dbs",
    "Hsbc",
    "Maybank",
    "Ocbc",
    "StandardChartered",
    "Trust",
    "Uob",
    "banks",
]