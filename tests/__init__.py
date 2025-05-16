from flask_bauto import AutoBlueprint, BullStack, dataclass, relationship

class Test(AutoBlueprint):
    @dataclass
    class Genus:
        name: str
        family: str
        species: relationship = None
        #species: relationship = relationship('Species', back_populates='genus', cascade="all, delete-orphan")

        def __str__(self):
            return self.name
        
    @dataclass 
    class Species:
        genus_id: int
        name: str
        
    def show_species(self) -> str:
        return f"{self.query.genus.get(1).species_list}"

bs = BullStack(__name__, [Test(enable_crud=True)])

def create_app():
    return bs.create_app()
