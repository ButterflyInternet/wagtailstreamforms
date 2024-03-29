import json

from django import forms
from django.core import exceptions
from django.db import models
from django.utils.text import capfirst
from wagtail.core import blocks

from wagtailstreamforms import hooks
from wagtailstreamforms.utils.apps import get_app_submodules

_fields = {}
_searched_for_fields = False


def register(field_name, cls=None):
    """
    Register field for ``field_name``. Can be used as a decorator::
        @register('singleline')
        class SingleLineTextField(BaseField):
            field_class = django.forms.CharField
    or as a function call::
        class SingleLineTextField(BaseField):
            field_class = django.forms.CharField
        register('singleline', SingleLineTextField)
    """

    if cls is None:
        def decorator(cls):
            register(field_name, cls)
            return cls

        return decorator

    _fields[field_name] = cls


def search_for_fields():
    global _searched_for_fields
    if not _searched_for_fields:
        list(get_app_submodules('wagtailstreamforms_fields'))
        _searched_for_fields = True


def get_fields():
    """ Return the registered field classes. """

    search_for_fields()
    return _fields


class BaseField:
    """A base form field class, all form fields must inherit this class.

    Usage::

        @register('multiline')
        class MultiLineTextField(BaseField):
            field_class = forms.CharField
            widget = forms.widgets.Textarea
            icon = 'placeholder'
            label = 'Text (multi line)'

    """

    field_class = None
    widget = None
    icon = 'placeholder'
    label = None

    def get_formfield(self, block_value):
        """
        Get the form field. Its unlikely you will need to override this.

        :param block_value: The StreamValue for this field from the StreamField
        :return: An instance of a form field class, ie ``django.forms.CharField(**options)``
        """

        if not self.field_class:
            raise NotImplementedError('must provide a cls.field_class')

        options = self.get_options(block_value)

        if self.widget:
            return self.field_class(widget=self.widget, **options)

        return self.field_class(**options)

    def get_options(self, block_value):
        """The field options.

        Override this to provide additional options such as ``choices`` for a dropdown.

        :param block_value: The StreamValue for this field from the StreamField
        :return: The options to be passed into the field, ie ``django.forms.CharField(**options)``
        """
        label = block_value.get('label')
        data = {
            'label': label,
            'help_text': block_value.get('help_text'),
            'required': block_value.get('required'),
            'initial': block_value.get('default_value')
        }
        if block_value.get('error_messages'):
            try:
                error_messages = json.loads(block_value.get('error_messages'))
                for k in error_messages.keys():
                    if '{label}' not in error_messages[k]:
                        continue
                    if error_messages[k].startswith('{label}'):
                        error_messages[k] = error_messages[k].format(label=label.capitalize())
                    else:
                        error_messages[k] = error_messages[k].format(label=label.lower())

                data.update({'error_messages': error_messages})
            except:
                pass
        return data

    def get_form_block(self):
        """The StreamField StructBlock.

        Override this to provide additional fields in the StreamField.

        :return: The ``wagtail.core.blocks.StructBlock`` to be used in the StreamField
        """
        return blocks.StructBlock([
            ('label', blocks.CharBlock()),
            ('help_text', blocks.CharBlock(required=False)),
            ('required', blocks.BooleanBlock(required=False)),
            ('error_messages', blocks.CharBlock(required=False,
                                                default='{"required": "Please enter {label}"}',
                                                help_text='Available variable: `{label}`, example: {"required": "Please enter {label}"}')),
            ('default_value', blocks.CharBlock(required=False)),
        ], icon=self.icon, label=self.label)


class HookMultiSelectFormField(forms.MultipleChoiceField):
    widget = forms.CheckboxSelectMultiple


class HookSelectField(models.Field):

    def get_choices_default(self):
        return [
            (fn.__name__, capfirst(fn.__name__.replace('_', ' ')))
            for fn in hooks.get_hooks('process_form_submission')
        ]

    def get_db_prep_value(self, value, connection=None, prepared=False):
        if isinstance(value, str):
            return value
        elif isinstance(value, list):
            return ",".join(value)

    def get_internal_type(self):
        return "TextField"

    def formfield(self, **kwargs):
        defaults = {
            'form_class': HookMultiSelectFormField,
            'choices': self.get_choices_default()
        }
        defaults.update(kwargs)
        return super().formfield(**defaults)

    def from_db_value(self, value, expression, connection, context):
        if value is None or value == '':
            return []
        return value.split(',')

    def to_python(self, value):
        if not value or value == '':
            return []
        if isinstance(value, list):
            return value
        return value.split(',')

    def validate(self, value, model_instance):
        arr_choices = [v for v, s in self.get_choices_default()]
        for opt in value:
            if opt not in arr_choices:
                raise exceptions.ValidationError('%s is not a valid choice' % opt)
        return
