import re
from abc import ABC
from enum import Enum
from datetime import date
from itertools import count
from typing import List, Optional
from pydantic import BaseModel, Field
from eBonsParser.utils import extract_text_from_pdf
from eBonsParser.models.item import *
from eBonsParser.models.payment import PaymentMethod, PaymentMethodType

class Address(BaseModel):
    street: str
    city: str
    zip: int

class StoreType(Enum):
    SUPERMARKET = "supermarket"
    BEAUTY = "beauty"
    CLOTHING = "clothing"
    FURNITURE = "furniture"
    GARDEN = "garden"
    LIBRARY = "library"
    TOYS = "toys"
    SPORTS = "sports"
    PHARMACY = "pharmacy"
    ELECTRONICS = "electronics"


class Store(BaseModel,ABC):
    name: str
    type: StoreType
    UID : str = None
    id: int = Field(default_factory=count().__next__)
    address: Optional[Address] = None
    phone: Optional[str] = None

    def _address_extract(self,raw_text: str) -> "Address":
            """
            Extracts the address from the raw text of the receipt.
            """
            address_match_1 = re.search(r'[\s\*]*([a-zäöüß \d.,-]+?)\s*[\s\*]*(\d{5})\s*([a-zäöüß \d.,-]+)[\s\*]*', raw_text, re.IGNORECASE)
            address_match_2 = re.search(r'([\wäöüß \d.,-]+),\s*(\d{5})\s*([\wäöüß \d.,-]+)', raw_text, re.IGNORECASE)

            if address_match_1:
                return Address(
                    street=address_match_1.group(1).replace('  ', ' ').replace(',', '').strip(),
                    zip=address_match_1.group(2),
                    city=address_match_1.group(3).strip()
                )
            elif address_match_2:
                return Address(
                    street=address_match_2.group(1).replace('  ', ' ').replace(',', '').strip(),
                    zip=address_match_2.group(2),
                    city=address_match_2.group(3).strip()
                )
            else:
                raise ValueError("Address not found in the receipt text.") 
            
    def _phone_extract(self, raw_text: str) -> str:
        """
        Extracts the phone number from the raw text of the receipt.
        """
        phone_match = re.search(r"^(Tel\.?:?|Telefon:?)\s*(.*)", raw_text, re.MULTILINE)
        if phone_match:
            return phone_match.group(2).strip()
        else:
            raise ValueError("Phone number not found in the receipt text.")

    def _uid_extract(self, raw_text: str) -> str:
        """
        Extracts the UID from the raw text of the receipt.
        """
        pass
        uid_match = re.search(r"^(UID|Steuernummer\s?(Nr)?\.?:?|UID:?.?\s?)\s*(.*)", raw_text, re.MULTILINE)
        if uid_match:
            return uid_match.group(3).strip()
        else:
            raise ValueError("UID not found in the receipt text.")

    def _items_extract(self, ebon_list: List) -> List[Item]:
        """
        Extracts the Items from the raw text of the receipt.
        """
        collect = False
        items = []
        if self.name == "REWE Markt GmbH":
            for line in ebon_list:
                if line == "-"*38:
                    collect = False
                    break
                if line == "EUR":
                    collect = True
                    continue
                if collect:
                    normalized_line = re.sub(r"(\d+),(\d{2})", r"\1.\2", line).strip()
                    item_match = re.match(r"^(.*\S)\s+(\d+\.\d{2})\s+([AB])$", normalized_line)
                    item_match_weight = re.match(r"([\d.]+)\s*(kg|g|l|ml|pcs)\s*x\s*[\d.]+\s*EUR/?kg", normalized_line, re.IGNORECASE)
                    pfand_match = re.match(r"^(PFAND)\s+\d+\.\d{2}\s+EURO\s+(\d+\.\d{2})\s+([AB])", normalized_line)
                    if item_match:
                        item_name = item_match.group(1).strip()
                        item_price = float(item_match.group(2))
                        item_tax_class = TaxClass.REGULAR if item_match.group(3) == "A" else TaxClass.REDUCED
                        current_item = Item(
                            name=item_name,
                            price=item_price,
                            tax_class=item_tax_class.value if item_tax_class else None,
                            unit=None,
                            quantity=None
                        )
                        items.append(current_item)
                    elif item_match_weight and items:
                        weight = float(item_match_weight.group(1))
                        unit = item_match_weight.group(2).lower()
                        unit_enum = QuantityUnit(unit.lower()) if unit != "pcs" else QuantityUnit.PCS
                        items[-1].unit = unit_enum.value
                        items[-1].weight = weight
                    elif pfand_match:
                        item_name = pfand_match.group(1)
                        item_price = float(pfand_match.group(2))
                        item_tax_class = TaxClass.REGULAR if pfand_match.group(3) == "A" else TaxClass.REDUCED
                        current_item = Item(
                            name="PFAND",
                            price=item_price,
                            tax_class=item_tax_class.value,
                            unit=None,
                            weight=None,
                            description="(Pfand)"
                        )
                        items.append(current_item)
        elif self.name == "Thalia":
            for line in ebon_list:
                if line == "-"*11:
                    collect = False
                    break
                if "Art/EAN" in line:
                    collect = True
                    continue
                if collect:
                    normalized_line = re.sub(r"(\d+),(\d{2})", r"\1.\2", line).strip()
                    item_match = re.match(r"^(.*\S)\s+(\d+\.\d{2})\s+([1|2])$", normalized_line)
                    if item_match:
                        item_name = item_match.group(1).strip()
                        item_price = float(item_match.group(2))
                        item_tax_class = TaxClass.REGULAR if item_match.group(3) == "2" else TaxClass.REDUCED
                        current_item = Item(
                            name=item_name,
                            price=item_price,
                            tax_class=item_tax_class.value if item_tax_class else None,
                            unit=None,
                            quantity=None
                        )
                        items.append(current_item)
        return items

    def _sum_extract(self, raw_text: str) -> float:
        """
        Extracts the sum from the raw text of the receipt.
        """
        sum_match = re.search(r"^(SUMME\s?(.*)\s*EUR)\s*(.*)", raw_text, re.MULTILINE)
        if sum_match:
            normalized_line = re.sub(r"(\d+),(\d{2})", r"\1.\2", sum_match.group(3)).strip()
            return float(normalized_line)
        else:
            raise ValueError("Sum not found in the receipt text.")

    def _payment_extract(self, raw_text: str) -> PaymentMethod:
        """
        Extracts the Payment method from the raw text of the receipt.
        """
        payment_match = re.search(r"^(Geg\.?\s*)([\w\-]+)\s*EUR\s?(.*)|Contactless\s*", raw_text, re.MULTILINE)
        if payment_match:
            if payment_match.group(3) == "BAR":
                method = PaymentMethodType.CASH
            else:
                method = PaymentMethodType.CARD
            card_number_match = re.search(r"Nr\.?\s*#+\s*(\d{4}\s*\d{4})", raw_text, re.MULTILINE)
            if card_number_match:
                card_number = card_number_match.group(1).strip()
            else:
                card_number = None
            return PaymentMethod(
                method=method,
                card=card_number if method == PaymentMethodType.CARD else None)
        else:
            raise ValueError("Payment Method not found in the receipt text.")
        
    def _date_extract(self, raw_text: str) -> date:
        """
        Extracts the date from the raw text of the receipt.
        """
        date_match = re.search(r"(\d{2})[.\-/](\d{2})[.\-/](\d{4})", raw_text, re.MULTILINE)
        if date_match:
            day, month, year = map(int, date_match.groups())
            return date(year, month, day)
        else:
            raise ValueError("Date not found.")

    def _bonNr_extract(self, raw_text: str) -> float:
        """
        Extracts Bon Number from the raw text of the receipt.
        """
        ebon_match = re.search(r"\bBon-Nr\.?:?\s*(\d{1,10})|Beleg-Nr\.?:?\s*(\d{1,10})\b", raw_text)
        if ebon_match:
            return ebon_match.group(1).strip()
        else:
            raise ValueError("Bon Number not found in the receipt text.")  
        
    def _REWEbonus_extract(self, raw_text: str) -> float:
        bonus_match  = re.search(r"\bdu\s*(\d+(,\d{2}))\s*EUR(\\n|\s*)REWE\s*Bonus\b", raw_text)
        if bonus_match:
            normalized_value = re.sub(r"(\d+),(\d{2})", r"\1.\2",bonus_match.group(1)).strip()
            return float(normalized_value)

        else:
            return None

    def parse_ebon(self, ebon_pdf):
        from eBonsParser.models.receipt import Receipt  
        """
        Parses a PDF receipt file into a Receipt model.
        """
        ebon_text = extract_text_from_pdf(ebon_pdf)
        self.address = self._address_extract(ebon_text)
        self.phone = self._phone_extract(ebon_text)
        self.UID = self._uid_extract(ebon_text)
        ebonNr = self._bonNr_extract(ebon_text)
        bonus_amount = self._REWEbonus_extract(ebon_text)
        listed_ebon = ebon_text.splitlines()
        items = self._items_extract(listed_ebon)
        total = self._sum_extract(ebon_text)
        payment_method = self._payment_extract(ebon_text)
        date = self._date_extract(ebon_text)
        return Receipt(
            ebonNr=ebonNr,
            store=self,
            items=items,
            total=total,
            payment_method=payment_method,
            rewe_bonus=bonus_amount,
            date=date
        )