from flask_bauto import AutoBlueprint, BullStack, dataclass, relationship, File
from datetime import datetime, date
from pathlib import Path

class Test(AutoBlueprint):
    @dataclass
    class Genus:
        name: str
        family: str
        species: relationship = None
        #species: relationship = relationship('Species', back_populates='genus', cascade="all, delete-orphan")

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
        #recorded: date
        #experiment_file: Path
        
    def show_species(self) -> str:
        return f"{self.query.genus.get(1).species_list}"

bs = BullStack(__name__, [Test(enable_crud=True,url_prefix=False)])

def create_app():
    return bs.create_app()
