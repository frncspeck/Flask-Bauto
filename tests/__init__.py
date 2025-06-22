from flask_bauto import AutoBlueprint, dataclass, relationship, File
from bull_stack import BullStack
from datetime import datetime, date
from pathlib import Path
from typing import Annotated

class Test(AutoBlueprint):
    @dataclass
    class Genus:
        name: str
        family: str
        extant: str = 'yes'
        description: str = None
        species: list[int] = None
        #species: list[int] = relationship('Species', back_populates='genus', cascade="all, delete-orphan")

        def __str__(self):
            return self.name

        @property
        def actions(self):
            return [
                (f"/user/admin/profile/{self.id}", 'bi bi-app'),
                (f"/user/remove/{self.id}", 'bi bi-x-circle')
            ]
        
    @dataclass 
    class Species:
        genus_id: int
        name: str
        image: Annotated[Path,{'storage_location':'species'}]
        #recorded: date

class OtherTest(AutoBlueprint):
    @dataclass
    class Crop:
        species_id: int
        name: str
        description: str = None
        crop_variety: list[int] = None

    @dataclass
    class CropVariety:
        crop_id: int
        name: str
        
    def show_forensics(self) -> str:
        c = self.query.crop.get(1)
        return f"User id {c._user_id}, time of last mod {c._mod_datetime}"

bs = BullStack(__name__, [
    Test(enable_crud=True,url_prefix=False,forensics=False),
    OtherTest(enable_crud=True,forensics=True)
], admin_init_password='badmin')

def create_app():
    return bs.create_app()

