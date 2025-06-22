import os
import inspect
from types import SimpleNamespace
from collections import OrderedDict
from dataclasses import dataclass, field, MISSING
import datetime
import logging
from flask import Blueprint, render_template, redirect, flash, url_for, send_file
from flask_wtf import FlaskForm
from wtforms import Form, FormField, Field, FieldList, StringField, TextAreaField, \
    PasswordField, EmailField, SubmitField, SelectField, BooleanField, \
    IntegerField, FloatField, DateTimeField, DateField, TimeField, FileField
from wtforms.validators import InputRequired, DataRequired, Optional
from sqlalchemy import Table, Column, Integer, String, ForeignKey, \
    DateTime, Date, Time
from sqlalchemy.orm import registry, relationship
from flask_bauto.types import BauType, File, OneToManyList, Bauhaus
            
class AutoBlueprint:
    """An automated blueprint for flask based on inner dataclass definitions

    The `AutoBlueprint` was created to avoid conceptual code duplication
    between creating `sqlalchemy` database classes and `wtforms` forms.
    Simply by using annotated (type-hinted) inner dataclasses from classes
    inheriting from this class, all necessary components are made dynamically.

    Attributes
    ----------
    name : str
        the blueprint name, made available as app extension and used in route
    fair_data : bool
        if True, all data of blueprint is readable (default True)
    forensics : bool
        if True, track time and user of data table modifications (default False)
    protect : bool | str | None
        if True, only registered users can add/modify data, if provided as a str
        only users with the specified role. False or None should only be used
        for testing
    url_prefix : str
        the prefix used for the blueprint
    url_routes : dict
        names and routes dict
    index_page : str
        html template for blueprint index
    _import_route : bool
        enable db import
    _export_route : bool
        enable db export

    Methods
    -------
    init_app(app)
        initializes the Flask app
        
    """
    
    def __init__(
            self, app=None, registry=registry(), url_prefix=None, enable_crud=False,
            fair_data=True, forensics=False, protect_data=True, imex=True,
            protect_index=False, index_page='base.html'):
        """
        Parameters
        ----------
        name : str
            the blueprint name, made available as app extension and used in route
        fair_data : bool
            if True, all data of blueprint is readable (default True)
        forensics : bool
            if True, track time and user of data table modifications (default False)
        protect_data : bool | str | None
            if True, only registered users can add/modify data
        url_prefix : str
            the prefix used for the blueprint
        url_routes : dict
            names and routes dict
        index_page : str
            html template for blueprint index        
        """
        
        self.name = self.__class__.__name__.lower()
        self.fair_data = fair_data
        self.forensics = forensics # track user and time of modifications
        self.protect = protect_data
        self.protect_index = protect_index
        self.url_prefix = '' if url_prefix is False else f"/{url_prefix or self.name}"
        self.url_routes = {}
        self.index_page = index_page
        if imex:
            self._import_route = True
            self._export_route = True

        # Set up logging
        self.logger = logging.getLogger(self.name)

        # Set up registry
        self.mapper_registry = registry# or self.registry
        # To allow sibling AutoBlueprint's to find models in each other's namespaces
        # a registry is defined during the AutoBlueprint definition
        
        # Register models and forms
        self._set_bauprints()
        self.register_models()
        self.register_forms()

        self.blueprint = Blueprint(
            f"{self.name}_blueprint", __name__,
            url_prefix=self.url_prefix,
            template_folder='templates'
        )

        # Routes
        self.add_url_rules()
        if enable_crud:
            self.enable_crud = self.models if enable_crud is True else enable_crud
            self.add_url_crud_rules()

    def init_app(self, app):
        """
        Parameters
        ----------
        app : flask.Flask
            Flask application

        Raises
        ------
        Warning
            If no frontend fefset extension is detected, raises a warning
        """
        app.extensions[self.name] = self
        app.register_blueprint(
            self.blueprint, url_prefix=self.url_prefix
        )
        self.db = app.extensions['sqlalchemy']
        with app.app_context():
            self.mapper_registry.metadata.create_all(self.db.engine)
        
        # Set menu
        if 'fefset' in app.extensions:
            fef = app.extensions['fefset']
            fef.add_submenu(self.name)
            for name, route in self.url_routes.items():
                fef.add_menu_entry(
                    name, route['route'], submenu=self.name, role=route['role']
                )
        else:
            app.logger.warning(
                'Frontend not available, operating in headless mode.'
                'If this is unintended, be sure to init "fefset" before extension'
            )

    @classmethod
    def defined_models(cls):
        """
        Returns
        -------
        list
            a list of strings representing the data models
        """
        try: cls_code = inspect.getsource(cls)
        except OSError:
            #from IPython.core.oinspect import getsource
            cls_code = '' #getsource(cls)
        datamodels = inspect.getmembers(cls, lambda x: inspect.isclass(x) and x is not type)
        def linenumber_of_member(m):
            try:
                return m[1].__class__.__code__.co_firstlineno
            except AttributeError:
                return -1
        if cls_code: datamodels.sort(key=lambda x: cls_code.index(f"class {x[0]}:"))
        else:
            import warnings
            warnings.warn(
                'Interactive defined blueprints might not have functional relationships'
            )
        # Transform into ordereddict
        datamodels = OrderedDict([
            (cls.camel_to_snake(name), dm)
            for name, dm in datamodels
        ])
        return datamodels

    @classmethod
    def all_defined_models(cls):
        datamodels = OrderedDict()
        for subcls in cls.__base__.__subclasses__():
            datamodels.update(subcls.defined_models())
        return datamodels

    @property
    def datamodels(self):
        return self.defined_models()

    @property
    def all_models(self):
        return self.all_defined_models()
        
    def db_transform(self, data, model_name):
        """Tranform ux provided data to db format

        Arguments
        ---------
            data: dict
                The data dictionary with column name keys and corresponding data
                The values in this dictionary get transformed
        """
        for fieldname, fieldtype in self.models[
                model_name
        ].__annotations__.items():
            if fieldname not in data: continue
            bautype = BauType._get_bautype(fieldtype)
            if bautype.ux2py:
                data[fieldname] = bautype(ux_item=data[fieldname]).db_item

    def _get_default(self, model, fieldname):
        return (
            model.__dataclass_fields__[fieldname].default if
            model.__dataclass_fields__[fieldname].default != MISSING
            else model.__dataclass_fields__[fieldname].default_factory
        )

    def _set_bauprint(self, model_name, model):
        """This method manipulates a model which should be an
        internal dataclass
        """
        model.__bauprint__ = OrderedDict([
            (
                name,
                Bauhaus(
                    name, model_name,
                    BauType._get_bautype(type),
                    self._get_default(model, name)
                )
            ) for name, type in model.__annotations__.items()
            if type != list[int] or name.startswith('_')
        ])

    def _set_bauprints(self):
        """Set `__bauprint__` for each of the defined models
        """
        for name, model in self.datamodels.items():
            self._set_bauprint(name, model)
    
    def register_forms(self):
        self.forms = {}
        for name, dm in self.datamodels.items():
            class ModelForm(FlaskForm):
                pass

            for fieldname, fieldtype in dm.__annotations__.items():
                if fieldtype == list[int]: continue
                default_value = dm.__bauprint__[fieldname].default
                if fieldname.endswith('_id') and fieldname[:-3] in self.all_models:
                    model = self.all_models[fieldname[:-3]]
                    setattr(
                        ModelForm,
                        fieldname,
                        SelectField(
                            fieldname.replace('_',' ').capitalize(),
                            # lambda required default model as otherwise the last reference to model is used
                            choices=lambda model=model: [(i.id,i) for i in self.db.session.query(model).all()]
                        )
                    ) # TODO allow blank option if default is None
                else: setattr(
                    ModelForm,
                    fieldname,
                    # Primitive types
                    BauType._get_bautype(fieldtype).ux_type(
                        fieldname.replace('_',' ').capitalize(),
                        validators=(
                            [] if fieldtype is bool else [
                                Optional() if default_value is None else InputRequired()
                            ]
                        ),
                        default=None if default_value is MISSING else default_value
                    )
                )
            setattr(ModelForm, 'submit', SubmitField(f'Submit "{name}"'))
            self.forms[name.lower()] = ModelForm

    def register_models(self):
        cls = self.__class__
        self.models = {}
        self.model_properties = {}
        for name, dm in self.datamodels.items():
            self.model_properties[name] = {}
            columns = {
                colname: coltype.create_db_column(self)
                for colname, coltype in dm.__bauprint__.items()
            }
            if self.forensics:
                from flask_login import current_user
                columns['_user_id'] = Column('_user_id', Integer, default=lambda: current_user.id, nullable=False)
                columns['_mod_datetime'] = Column('_mod_datetime', DateTime, default=datetime.datetime.now, nullable=False)
            table = Table(
                name.lower(),
                self.mapper_registry.metadata,
                Column("id", Integer, primary_key=True),
                *columns.values()
            )

            # One to many relationships for model
            for colname, coltype in dm.__annotations__.items():
                if coltype == list[int]:
                    self.model_properties[name][colname+'_list'] = (
                        getattr(dm, colname) or
                        relationship(
                            self.snake_to_camel(colname),
                            back_populates=name.lower()
                        )
                    )
                    columns[colname+'_list'] = None
            
            self.mapper_registry.map_imperatively(dm, table, properties=self.model_properties[name])

            # Set data headers and columns if not set at class definition
            if not hasattr(dm, '_data_raw_attributes'): # db column names
                dm._data_raw_attributes = [c for c in columns.keys() if not c.startswith('_')]
            if not hasattr(dm, '_data_attributes'): # db column names
                dm._data_attributes = [c[:-3] if c.endswith('_id') else c for c in dm._data_raw_attributes]
            if not hasattr(dm, '_data_headers'):
                dm._data_headers = [c.replace('_',' ').capitalize() for c in dm._data_attributes]
            if not hasattr(dm, '_data_columns'):
                dm._data_columns = property(
                    lambda self: [
                        OneToManyList(
                            quantity = len(getattr(self,c)),
                            _self_reference_url = f"{self._self_reference_url}/{c}",
                            _add_action = f"{self._self_reference_add}/{c}"
                        ) if c.endswith('_list') else
                        getattr(self,c) for c in self._data_attributes
                    ]
                )

            # Set self-reference urls
            dm._self_reference_url = property(
                lambda self, url_prefix=self.url_prefix, model=name.lower():
                f"{url_prefix}/{model}/read/{self.id}"
            )
            dm._self_reference_add = property(
                lambda self, url_prefix=self.url_prefix, model=name.lower():
                f"{url_prefix}/{model}/update/{self.id}/add"
            )
            
            # Set standard actions
            if not hasattr(dm, '_actions'):
                dm._actions = property(
                    lambda self, url_prefix=self.url_prefix, model=name.lower():
                    [
                        (f"{url_prefix}/{model}/read/{self.id}", 'bi bi-zoom-in'),
                        (f"{url_prefix}/{model}/update/{self.id}", 'bi bi-pencil'),
                        (f"{url_prefix}/{model}/delete/{self.id}", 'bi bi-x-circle')
                    ]
                )
            
            self.models[name.lower()] = dm
        
    def add_url_crud_rules(self):
        for name in self.enable_crud:
            # Create
            self.add_url_rule(
                f"/{name}/create", f"{name}_create", 
                view_func=self.create, defaults={'name':name},
                methods=['GET','POST']
            )
            self.url_routes[f"Create {name}"] = {
                'route':f"{self.url_prefix}/{name}/create",
                'role':f"{self.name}_admin"
            }
            # List
            self.add_url_rule(
                f"/{name}/list", f"{name}_list", 
                view_func=self.list, defaults={'name':name},
                methods=['GET'], protect=not(self.fair_data)
            )
            self.url_routes[f"List {name}"] = {
                'route': f"{self.url_prefix}/{name}/list",
                'role': False
            }
            # Read
            self.add_url_rule(
                f"/{name}/read/<int:id>", f"{name}_read", 
                view_func=self.read, defaults={'name':name},
                methods=['GET'], protect=not(self.fair_data)
            )
            self.add_url_rule(
                f"/{name}/read/<int:id>/<list_attribute>", f"{name}_read", 
                view_func=self.read, defaults={'name':name},
                methods=['GET'], protect=not(self.fair_data)
            )
            # Update
            self.add_url_rule(
                f"/{name}/update/<int:id>", f"{name}_update", 
                view_func=self.update, defaults={'name':name},
                methods=['GET','POST']
            )
            self.add_url_rule(
                f"/{name}/update/<int:id>/add/<list_attribute>", f"{name}_update_attribute", 
                view_func=self.update, defaults={'name':name},
                methods=['GET','POST']
            )
            # Delete
            self.add_url_rule(
                f"/{name}/delete/<int:id>", f"{name}_delete", 
                view_func=self.delete, defaults={'name':name},
                methods=['GET','POST']
            )
            # Export rule
            if self._export_route:
                self.add_url_rule(
                    f"/{name}/export", f"{name}_export", 
                    view_func=self.export_route, defaults={'name':name},
                    methods=['GET']
                )
        # Full import rule
        if self._import_route:
            self.add_url_rule(
                '/import/db', 'import_db', 
                view_func=self.import_all_route,
                methods=['GET','POST']
            )
            self.url_routes['Import'] = {
                'route': f"{self.url_prefix}/import/db",
                'role': 'admin'
            }
        # Full export rule
        if self._export_route:
            self.add_url_rule(
                f"/export/db", 'full_export', 
                view_func=self.export_all_route, methods=['GET']
            )
            self.url_routes['Export'] = {
                'route': f"{self.url_prefix}/export/db",
                'role': 'admin'
            }

    def add_url_rule(self, *args, protect=None, **kwargs):
        """Wrapper around blueprint.add_url_rule
        adding protection if enabled on AutoBlueprint
        """
        from flask_iam import login_required, role_required
        if (protect in (None,True) or isinstance(protect,str)) and self.protect:
            if isinstance(protect,str): # Custom set role protection
                kwargs['view_func'] = role_required(protect)(kwargs['view_func'])
            elif isinstance(self.protect,str): # Blueprint level role protection
                kwargs['view_func'] = role_required(self.protect)(kwargs['view_func'])
            else: # Standard login_required protection
                kwargs['view_func'] = login_required(kwargs['view_func'])
        return self.blueprint.add_url_rule(*args, **kwargs)
    
    def add_url_rules(self, methods=['GET','POST']):
        if self.index_page:
            self.blueprint.add_url_rule('/', 'index', view_func=self.index, methods=['GET'])
            self.url_routes[self.name] = {'route': f"{self.url_prefix}/", 'role': False}
        cls = self.__class__
        viewfunctions = inspect.getmembers(
            cls,
            lambda x: inspect.isroutine(x)
            and hasattr(x,'__annotations__')
            and x.__annotations__.get('return',None) == str # TODO View type
        )
        for name, viewfunction in viewfunctions:
            self.blueprint.add_url_rule(f"/{name}", name, view_func=viewfunction, methods=['GET'], defaults={'self':self})
            self.url_routes[name] = {'route': f"{self.url_prefix}/{name}", 'role': False}

    # Database utilities
    @property
    def query(self):
        return SimpleNamespace(**{
            key:self.db.session.query(model) for key,model in self.models.items(
        )})
    
    # Predefined views without annotation as they are automatically added
    def index(self):
        return render_template(self.index_page)
        
    def create(self, name):
        form = self.forms[name]()
        setattr(form, 'submit', SubmitField(f'Submit "{name}"'))
        if form.validate_on_submit():
            # Make model instance
            data = {
                k:form.data[k]
                for k in form.data.keys() - {'submit','csrf_token'}
            }
            # Check if db transform is required for any of the columns
            self.db_transform(data, name)
            item = self.models[name](**data)
            self.db.session.add(item)
            self.db.session.commit()

            flash(f"{name} instance was created")

            return redirect(url_for(f"{self.name}_blueprint.{name}_list"))
        return render_template('uxfab/form.html', form=form, title=f"Create {name}")

    def list(self, name):
        items = self.db.session.query(self.models[name]).all()
        return render_template('bauto/list.html', items=items, title=f"List {name}")
        
    def read(self, name, id, list_attribute=None):
        item = self.db.session.query(self.models[name]).get_or_404(id)
        if list_attribute is None:
            form = self.forms[name](obj=item)
            form.submit.label.text = 'Info'
            for field in form:
                field.render_kw = {'disabled': 'disabled'}
            return render_template('uxfab/form.html', form=form, title=f"Info {name}")
        else: # Return list view of list attribute
            return render_template(
                'bauto/list.html',
                items=getattr(item,list_attribute),
                title=f"{list_attribute.capitalize()} of {name}"
            )

    def update(self, name, id, list_attribute=None):
        item = self.db.session.query(self.models[name]).get_or_404(id)
        if list_attribute:
            list_model_name = list_attribute[:-len('_list')]
            form = self.forms[list_model_name]()
            # Delete field for main model reference field
            delattr(form, name+'_id')
            if form.validate_on_submit():
                # Make model instance
                data = {
                    k:form.data[k]
                    for k in form.data.keys() - {'submit','csrf_token'}
                }
                # Check if db transform is required for any of the columns
                self.db_transform(data, list_model_name)
                data[name+'_id'] = id
                list_item = self.models[list_model_name](**data)
                self.db.session.add(list_item)
                self.db.session.commit()
                
                flash(f"{name} instance was created")
                
                return redirect(url_for(f"{self.name}_blueprint.{name}_list"))
            name = list_attribute

        # Normal update
        else:
            form = self.forms[name](obj=item)
            form.submit.label.text = 'Update'
            if form.validate_on_submit():
                # Make model instance
                data = {
                    k:form.data[k]
                    for k in form.data.keys() - {'submit','csrf_token'}
                }
                if self.forensics:
                    self.logger.info(
                        'Updating %s from user %s with %s by user %s',
                        item, data, item._user_id, current_user.id
                    )
                    item._user_id = current_user.id
                    item._mod_datetime = datetime.datetime.now()
                # Check if db transform is required for any of the columns
                self.db_transform(data, name)
                for k in data:
                    setattr(item, k, data[k])
                self.db.session.add(item)
                self.db.session.commit()
                
                flash(f"{name} instance was updated")
                
                return redirect(url_for(f"{self.name}_blueprint.{name}_read", id=item.id))
        return render_template('uxfab/form.html', form=form, title=f"Update {name} for {item}")

    def delete (self, name, id):
        item = self.db.session.query(self.models[name]).get_or_404(id)
        form = self.forms[name](obj=item)
        form.submit.label.text = 'Delete'
        if form.validate_on_submit():
            if self.forensics:
                self.logger.warning(
                    'Deleting %s from user %s by user %s',
                    item, item._user_id, current_user.id
                )
            self.db.session.delete(item)
            self.db.session.commit()

            flash(f"{name} instance was deleted")

            return redirect(self.url_prefix)
        return render_template('uxfab/form.html', form=form, title=f"Delete {name}")

    def export_model(self, name):
        import csv
        import tempfile
        fp = tempfile.NamedTemporaryFile(suffix=f"_{name}.csv", mode='wt', delete_on_close=False)
        csvwriter = csv.writer(fp, delimiter = ',')
        # Get attributes
        model = self.models[name]
        columns = [
            a for a in model._data_raw_attributes
            if not a.endswith('_list') # skip one2many relationships
        ]
        if self.forensics:
            columns = ['id'] + columns + ['_user_id', '_mod_datetime']
        csvwriter.writerow(columns) # column names
        for record in getattr(self.query, name).all():
            csvwriter.writerow([getattr(record,a) for a in columns])
        fp.close()
        return fp

    def export_route(self, name, delete_tmp=True):
        fp = self.export_model(name)
        response = send_file(
            fp.name, mimetype='text/csv', download_name=f"{name}_export.csv",
            as_attachment=True
        )
        if delete_tmp:
            os.unlink(fp.name)
        return response

    def export_all_route(self, delete_tmp=True):
        import tempfile
        import zipfile
        with tempfile.NamedTemporaryFile(suffix='.zip', delete_on_close=False) as fp_zip:
            fp_zip.close()
            with zipfile.ZipFile(fp_zip.name, 'w') as ziparc:
                for model_name in self.models:
                    fp = self.export_model(model_name)
                    ziparc.write(fp.name, arcname=f"{model_name}.csv")
                    if delete_tmp:
                        os.unlink(fp.name)
            return send_file(
                fp_zip.name, mimetype='application/zip',
                download_name=f"{self.name}_full_export.zip",
                as_attachment=True
            )

    def import_model(self, name, fp_csv):
        model = self.models[name]
        columns = fp_csv.readline().strip().split(',')
        if self.forensics:
            forenkeys = {
                'id':int,
                '_user_id':int,
                '_mod_datetime':datetime.datetime.fromisoformat
            }
        for line in fp_csv:
            record = dict(zip(columns,line.strip().split(',')))
            if self.forensics:
                item = model(**{
                    k:model.__annotations__[k](v) for k,v in record.items()
                    if k not in forenkeys
                })
                for fkey in forenkeys:
                    setattr(item, fkey, forenkeys[fkey](record[fkey]))
            else:
                item = model(**{
                    k:model.__annotations__[k](v) for k,v in record.items()
                })
            self.db.session.add(item)
        self.db.session.commit()

    def import_all_route(self):
        class FileForm(FlaskForm):
            zip_archive = FileField()
            submit = SubmitField()
        form = FileForm()
        if form.validate_on_submit():
            import zipfile
            import io
            with zipfile.ZipFile(form.zip_archive.data.stream) as ziparc:
                for model_name in self.models:
                    fp_csv = ziparc.open(f"{model_name}.csv")
                    self.import_model(model_name, io.TextIOWrapper(fp_csv))
            return redirect('/')
        else:
            return render_template(
                'uxfab/form.html', form=form, title='Import db'
            )

    #Utility functions
    @staticmethod
    def snake_to_camel(snake_str, lowerCamelCase=False):
        if lowerCamelCase:
            components = snake_str.split('_')
            return components[0] + ''.join(
                word.capitalize() for word in components[1:]
            )
        else:
            return ''.join(word.capitalize() for word in snake_str.split('_'))
    
    @staticmethod
    def camel_to_snake(camel_str):
        import re
        # https://stackoverflow.com/questions/1175208/elegant-python-function-to-convert-camelcase-to-snake-case
        pattern = re.compile(
            r"""
            (?<=[a-z])      # preceded by lowercase
            (?=[A-Z])       # followed by uppercase
            |               #   OR
            (?<=[A-Z])      # preceded by uppercase
            (?=[A-Z][a-z])  # followed by uppercase, then lowercase
            """,
            re.X,
        )
        return pattern.sub('_', camel_str).lower()        
