"""Module defining types for use with Flask-Bauto"""

from dataclasses import dataclass, field
from collections import namedtuple
from collections.abc import Callable
from pathlib import Path
import datetime

# Form types
import wtforms as wtf

# DB types
import sqlalchemy as sa
from sqlalchemy.orm import registry, relationship

# Type definitions that also act as descriptors for use on instance instantiation
# TODO refactor to work with BauType instead of sql and wtform separate mappings
@dataclass
class BauType:
    py_type: type
    db_type: type
    ux_type: type
    conversion_method: Callable = None

    def __call__(self, *args, **kwargs):
        try:
            kwargs['metadata']['bautype'] = self
        except KeyError: kwargs['metadata'] = {'bautype': self}
        return field(*args, **kwargs)

    @classmethod
    def get_types(cls):
        return {
            t.py_type:t for t in cls.__subclasses__()
        }

@dataclass
class String(BauType):
    py_type: type = str
    db_type: type = sa.String
    ux_type: type = wtf.StringField

@dataclass
class Integer(BauType):
    py_type: type = int
    db_type: type = sa.Integer
    ux_type: type = wtf.IntegerField

@dataclass
class Float(BauType):
    py_type: type = float
    db_type: type = sa.Float
    ux_type: type = wtf.FloatField

@dataclass
class DateTime(BauType):
    py_type: type = datetime.datetime
    db_type: type = sa.DateTime
    ux_type: type = wtf.DateTimeField

@dataclass
class Date(BauType):
    py_type: type = datetime.date
    db_type: type = sa.Date
    ux_type: type = wtf.DateField

@dataclass
class Time(BauType):
    py_type: type = datetime.time
    db_type: type = sa.Time
    ux_type: type = wtf.TimeField

@dataclass
class File(BauType):
    storage_location: Path = None
    py_type: type = Path
    db_type: type = sa.String
    ux_type: type = wtf.FileField

@dataclass
class OneToManyList:
    quantity: int
    _self_reference_url: str
    _add_action: str = None

    def __str__(self):
        return str(self.quantity)

# class DateTimeField(Field):
#     def __init__(self, label=None, validators=None, **kwargs):
#         super().__init__(label, validators, **kwargs)
#         self.date_field = DateField(validators=[DataRequired()])
#         self.time_field = TimeField(validators=[DataRequired()])

#     def process_formdata(self, valuelist):
#         if valuelist and len(valuelist) == 2:
#             try:
#                 date_value = datetime.strptime(valuelist[0], "%Y-%m-%d").date()
#                 time_value = datetime.strptime(valuelist[1], "%H:%M").time()
#                 self.data = datetime.combine(date_value, time_value)
#             except ValueError:
#                 self.data = None
#                 raise ValueError("Invalid date/time format.")
