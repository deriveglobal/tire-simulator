from sqlalchemy import Column, Integer, String, Float, ForeignKey, Date
from sqlalchemy.orm import relationship
from .db import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String, index=True)
    model_name = Column(String, index=True)
    size_string = Column(String, index=True)
    segment = Column(String, index=True)        # e.g. "Agricultural"
    category = Column(String, index=True)       # e.g. "Tractor Rear"
    radial_or_bias = Column(String, index=True) # "Radial" or "Bias"
    load_index = Column(String, nullable=True)
    speed_rating = Column(String, nullable=True)
    ply_rating = Column(String, nullable=True)

    # relationships
    costs = relationship("ProductCost", back_populates="product")
    competitor_prices = relationship("CompetitorPrice", back_populates="product")


class ProductCost(Base):
    __tablename__ = "product_costs"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), index=True)

    # main cost components per tire
    product_cost_usd = Column(Float, nullable=False)   # what you pay manufacturer
    freight_cost_usd = Column(Float, nullable=False)   # total freight per tire (all-in)
    duty_rate_pct = Column(Float, nullable=False)      # duty % on product cost
    domestic_ship_usd = Column(Float, nullable=False)  # average domestic shipping per tire

    product = relationship("Product", back_populates="costs")


class CompetitorPrice(Base):
    __tablename__ = "competitor_prices"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), index=True)
    competitor_name = Column(String, index=True)   # e.g. "Firestone", "BKT", "Dealer A"
    price_usd = Column(Float, nullable=False)
    source = Column(String, nullable=True)         # URL or "scraped", "manual"
    observed_at = Column(Date, nullable=True)      # date when this price was observed

    product = relationship("Product", back_populates="competitor_prices")

