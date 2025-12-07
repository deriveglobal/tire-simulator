# app/scrapers.py

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ScrapedOffer:
    """
    Minimal structure for a scraped competitor offer.
    We can expand this later when real scrapers are ready.
    """
    source: str          # e.g. "SimpleTire", "FarmTireWarehouse"
    title: str           # Product title from the site
    url: str             # Link to the product page
    price: Optional[float] = None  # Parsed price if available
    currency: str = "USD"
    in_stock: bool = True


def scrape_all_sources(size_string: str, segment: str = "", brand: str = "") -> List[ScrapedOffer]:
    """
    Placeholder aggregator.

    For now it just returns an empty list so your app runs
    without errors. Later we will implement real scraping logic
    for specific e-commerce websites.

    :param size_string: e.g. "480/80R42"
    :param segment: e.g. "AG"
    :param brand: e.g. "Lassa"
    """
    # TODO: implement real scrapers for:
    # - SimpleTire
    # - FarmTireWarehouse
    # - TiresEasy
    # and return a flat list of ScrapedOffer
    return []
