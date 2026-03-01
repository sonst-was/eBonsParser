from datetime import date
from typing import List
from pydantic import BaseModel
from eBonsParser.models.item import Item
from eBonsParser.models.base import Store 
from eBonsParser.models.payment import PaymentMethod

class Receipt(BaseModel):
    ebonNr: int
    store: Store
    date: date
    total: float
    payment_method: PaymentMethod
    rewe_bonus: float | None
    items: List[Item]
