import inspect
from dataclasses import dataclass, field
from collections import namedtuple
from collections.abc import Callable
import datetime
from flask import Blueprint, render_template, redirect, flash, url_for
from flask_wtf import FlaskForm
from wtforms import Form, FormField, Field, FieldList, StringField, TextAreaField, \
    PasswordField, EmailField, SubmitField, SelectField, BooleanField, \
    IntegerField, FloatField, DateTimeField, DateField, TimeField, FileField
from wtforms.validators import InputRequired, DataRequired, Optional
from sqlalchemy import Table, Column, Integer, String, ForeignKey, \
    DateTime, Date, Time
from sqlalchemy.orm import registry, relationship
from flask_bauto.types import BauType, File, OneToManyList
            
class AutoBlueprint:
    def __init__(self, app=None, url_prefix=None, enable_crud=False, index_page='base.html'):
        self.name = self.__class__.__name__.lower()
        self.url_prefix = '' if url_prefix is False else f"/{url_prefix or self.name}"
        self.url_routes = {}
        self.index_page = index_page
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
                fef.add_menu_entry(name, route, submenu=self.name)
        else:
            app.logger.warning(
                'Frontend not available, operating in headless mode.'
                'If this is unintended, be sure to init "fefset" before extension'
            )

    @property
    def datamodels(self):
        cls = self.__class__
        return inspect.getmembers(cls, lambda x: inspect.isclass(x) and x is not type)
    
    def get_sqlalchemy_column(self, name, type, model):
        if name.endswith('_id') and name[:-3] in self.models and type is int:
            self.model_properties[model][name[:-3]] = relationship(name[:-3].capitalize())
            return Column(name, Integer, ForeignKey(name[:-3]+".id"))
        else: return Column(name, BauType.get_types()[type].db_type)

    def register_forms(self):
        self.forms = {}
        for name, dm in self.datamodels:
            class ModelForm(FlaskForm):
                pass

            for fieldname, fieldtype in dm.__annotations__.items():
                if fieldtype is relationship: continue
                elif fieldname.endswith('_id') and fieldname[:-3] in self.models:
                    model = self.models[fieldname[:-3]]
                    setattr(
                        ModelForm,
                        fieldname,
                        SelectField(
                            fieldname.replace('_',' ').capitalize(),
                            # lambda required default model as otherwise the last reference to model is used
                            choices=lambda model=model: [(i.id,i) for i in self.db.session.query(model).all()]
                        )
                    )
                else: setattr(
                    ModelForm,
                    fieldname,
                    # Primitive types
                    BauType.get_types()[fieldtype].ux_type(
                        fieldname.replace('_',' ').capitalize(),
                        validators=([] if fieldtype is bool else [InputRequired()])
                    )
                )
            setattr(ModelForm, 'submit', SubmitField(f'Submit "{name}"'))
            self.forms[name.lower()] = ModelForm
    
    def register_models(self):
        cls = self.__class__
        self.mapper_registry = registry()
        self.models = {}
        self.model_properties = {}
        for name, dm in self.datamodels:
            self.model_properties[name] = {}
            columns = {
                colname[:-3] if colname.endswith('_id') else colname:
                self.get_sqlalchemy_column(colname,coltype,name)
                for colname, coltype in dm.__annotations__.items()
                if not coltype is relationship or colname.startswith('_')
            }
            table = Table(
                name.lower(),
                self.mapper_registry.metadata,
                Column("id", Integer, primary_key=True),
                *columns.values()
            )

            # One to many relationships for model
            for colname, coltype in dm.__annotations__.items():
                if coltype is relationship:
                    self.model_properties[name][colname+'_list'] = (
                        getattr(dm, colname) or
                        relationship(colname.capitalize(), back_populates=name.lower())
                    )
                    columns[colname+'_list'] = None
            
            self.mapper_registry.map_imperatively(dm, table, properties=self.model_properties[name])

            # Set data headers and columns if not set at class definition
            if not hasattr(dm, '_data_attributes'):
                dm._data_attributes = columns.keys()
            if not hasattr(dm, '_data_headers'):
                dm._data_headers = [c.capitalize() for c in columns.keys()]
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
            self.blueprint.add_url_rule(
                f"/{name}/create", f"{name}_create", 
                view_func=self.create, defaults={'name':name},
                methods=['GET','POST']
            )
            self.url_routes[f"Create {name}"] = f"{self.url_prefix}/{name}/create"
            # List
            self.blueprint.add_url_rule(
                f"/{name}/list", f"{name}_list", 
                view_func=self.list, defaults={'name':name},
                methods=['GET']
            )
            self.url_routes[f"List {name}"] = f"{self.url_prefix}/{name}/list"
            # Read
            self.blueprint.add_url_rule(
                f"/{name}/read/<int:id>", f"{name}_read", 
                view_func=self.read, defaults={'name':name},
                methods=['GET']
            )
            self.blueprint.add_url_rule(
                f"/{name}/read/<int:id>/<list_attribute>", f"{name}_read", 
                view_func=self.read, defaults={'name':name},
                methods=['GET']
            )
            # Update
            self.blueprint.add_url_rule(
                f"/{name}/update/<int:id>", f"{name}_update", 
                view_func=self.update, defaults={'name':name},
                methods=['GET','POST']
            )
            self.blueprint.add_url_rule(
                f"/{name}/update/<int:id>/add/<list_attribute>", f"{name}_update", 
                view_func=self.update, defaults={'name':name},
                methods=['GET','POST']
            )
            # Delete
            self.blueprint.add_url_rule(
                f"/{name}/delete/<int:id>", f"{name}_delete", 
                view_func=self.delete, defaults={'name':name},
                methods=['GET','POST']
            )

    def add_url_rules(self, methods=['GET','POST']):
        if self.index_page:
            self.blueprint.add_url_rule('/', 'index', view_func=self.index, methods=['GET'])
            self.url_routes[self.name] = f"{self.url_prefix}/"
        cls = self.__class__
        viewfunctions = inspect.getmembers(
            cls,
            lambda x: inspect.isroutine(x)
            and hasattr(x,'__annotations__')
            and x.__annotations__.get('return',None) == str # TODO View type
        )
        for name, viewfunction in viewfunctions:
            self.blueprint.add_url_rule(f"/{name}", name, view_func=viewfunction, methods=['GET'], defaults={'self':self})
            self.url_routes[name] = f"{self.url_prefix}/{name}"

    # Database utilities
    @property
    def query(self):
        nt = namedtuple('QueryModels', self.models.keys())
        return nt(*(self.db.session.query(model) for model in self.models.values()))
    
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
            self.db.session.delete(item)
            self.db.session.commit()

            flash(f"{name} instance was deleted")

            return redirect(self.url_prefix)
        return render_template('uxfab/form.html', form=form, title=f"Delete {name}")

@dataclass
class BullStack:
    name: str
    blueprints: list
    config_filename: str = None
    tasks_enabled: bool = False
    brand_name: str = None
    logo: str = None
    index_page: str = 'base.html'
    index_redirect: bool = None

    def create_app(self):
        import os
        from flask import Flask
        from flask_sqlalchemy import SQLAlchemy
        from flask_fefset import FEFset
        from flask_uxfab import UXFab
        from flask_iam import IAM
        #from sqlalchemy.orm import create_engine
        #engine = create_engine(DATABASE_URL, echo=True)
        self.app = Flask(self.name)

        # App configuration
        self.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        self.app.config['SECRET_KEY'] = os.urandom(12).hex()
        self.app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 # max 50MB upload
        if self.tasks_enabled:
            self.app.config.from_mapping(
                CELERY=dict(
                    broker_url=os.environ.get("CELERY_BROKER_URL"),#'sqla+sqlite:////tmp/celery.db'
                    result_backend=f"db+sqlite:///{os.path.join(self.app.instance_path,'shared/celery.db')}",
                    #os.environ.get("CELERY_RESULT_BACKEND", "rpc://"),
                    task_ignore_result=True,
                ),
            )
        if self.config_filename:
            self.app.config.from_pyfile(self.config_filename)

        # Instance dir
        if not os.path.exists(self.app.instance_path):
            self.app.logger.warning(
                'Instance path "%s" did not exist. Creating directory.',
                self.app.instance_path
            )
            os.makedirs(self.app.instance_path)
        
        # App extensions
        fef = FEFset(frontend='bootstrap4')
        if self.brand_name: fef.settings['brand_name'] = self.brand_name
        if self.logo: fef.settings['logo_url'] = os.path.join('/static', self.logo)
        fef.init_app(self.app)
        uxf = UXFab()
        uxf.init_app(self.app)
        db = SQLAlchemy(self.app)
        iam = IAM(db)
        iam.init_app(self.app)

        # Blueprint extensions
        for blueprint in self.blueprints:
            blueprint.init_app(self.app)

        @self.app.errorhandler(500)
        def internal_error(error):
            return render_template('500.html'), 500
         
        @self.app.route('/', methods=['GET'])
        def index():
            if self.index_redirect: return redirect(self.index_redirect)
            else: return render_template(self.index_page)

        return self.app

    def __call__(self, *args, run=False, **kwargs):
        if run:
            try: self.run(*args, **kwargs)
            except AttributeError:
                self.create_app()
                self.run(*args, **kwargs)
        else: return self.create_app()
            
    def run(self, *args, **kwargs):
        return self.app.run(*args, **kwargs)
