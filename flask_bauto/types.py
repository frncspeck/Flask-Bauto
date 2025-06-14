"""Module defining types for use with Flask-Bauto"""

from dataclasses import dataclass, field
from collections import namedtuple
from pathlib import Path
import datetime

# Python types
from typing import Annotated, get_origin, get_args, get_type_hints
#type markdown = Annotated[str, {'max_size':255}] # TODO 3.12+ type declaration
markdown = Annotated[str, {'max_size':255}] # TODO 3.12+ type declaration

# Form types
import wtforms as wtf

# DB types
import sqlalchemy as sa
from sqlalchemy.orm import registry, relationship

# Type definitions that also act as descriptors for use on instance instantiation
# TODO refactor to work with BauType instead of sql and wtform separate mappings
@dataclass
class BauType:
    py_item: any = None
    db_item: any = None
    ux_item: any = None
    py_type: type = None
    db_type: type = None
    ux_type: type = None
    config: namedtuple = None
    
    def __post_init__(self):
        if self.py_item is not None:
            if self.db_item is None:
                self.db_item = self.py2db()
            if self.ux_item is None:
                self.ux_item = self.py2ux()
        elif self.db_item is not None:
            if self.py_item is None:
                self.py_item = self.db2py()
            if self.ux_item is None:
                self.ux_item = self.py2ux()
        elif self.ux_item is not None:
            if self.py_item is None:
                self.py_item = self.ux2py()
            if self.db_item is None:
                self.db_item = self.py2db()
            
    def __call__(self, *args, **kwargs):
        try:
            kwargs['metadata']['bautype'] = self
        except KeyError: kwargs['metadata'] = {'bautype': self}
        return field(*args, **kwargs)

    # Default transform function names to False to check if transform required
    py2db = False
    py2ux = False
    db2py = False
    ux2py = False

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
    py_type: type = Path
    db_type: type = sa.JSON
    ux_type: type = wtf.FileField

    def ux2py(self):
        py_item = {
            'filename': self.ux_item.filename,
            'content_type': self.ux_item.content_type,
            'content_length': self.ux_item.content_length,
            'mimetype': self.ux_item.mimetype,
            'content': self.ux_item.stream.read().decode()
        }
        return py_item
    
    def py2db(self):
        #storage_location = self.config.storage_location
        # TODO get from type annotation
        #if storage_location == 'db':
        return self.py_item

@dataclass
class JSON(BauType):
    py_type: type = dict
    db_type: type = sa.JSON
    ux_type: type = wtf.FormField
    
@dataclass
class Task(BauType):
    py_type: type = callable
    db_type: type = sa.JSON
    # For this type the ux_type is intended for display and not input
    ux_type: type = wtf.TextAreaField
    
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
