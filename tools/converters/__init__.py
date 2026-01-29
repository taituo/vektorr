"""
Vektorr Data Converters - Transform provider data to internal format.

Supported providers:
- SportMonks (events + odds)
- The Odds API (odds only)
- BetsAPI (events + odds)
- CSV files (flexible column mapping)
"""
from .base_converters import (
    BaseConverter,
    SportMonksConverter,
    TheOddsApiConverter,
    BetsApiConverter,
    CSVConverter,
)
from .universal_converter import UniversalConverter, convert_file

__all__ = [
    # Base
    "BaseConverter",
    # Providers
    "SportMonksConverter",
    "TheOddsApiConverter",
    "BetsApiConverter",
    "CSVConverter",
    # Universal
    "UniversalConverter",
    "convert_file",
]
