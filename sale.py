# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import copy
from decimal import Decimal

from trytond.model import ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import And, Bool, Eval, Or, PYSONEncoder, If
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateTransition, StateView, Button

__all__ = ['Sale', 'SaleLine', 'SetQuantities', 'SetQuantitiesStart',
    'SetQuantitiesStartLine']


class Sale(metaclass=PoolMeta):
    __name__ = 'sale.sale'

    @classmethod
    def delete(cls, sales):
        with Transaction().set_context(no_update_template_qty=True):
            super(Sale, cls).delete(sales)


class SaleLine(metaclass=PoolMeta):
    __name__ = 'sale.line'

    template = fields.Many2One('product.template', 'Product Template',
        domain=[
            ('salable', '=', True),
            ],
        states={
            'invisible': Or(Eval('type') != 'line', Bool(Eval('product', 0))),
            'readonly': Or(Bool(Eval('product', 0)),
                Bool(Eval('template_childs'))),
            },
        depends=['type', 'product', 'template_childs'])
    template_parent = fields.Many2One('sale.line', 'Parent', domain=[
            ('type', '=', 'line'),
            ('template', '!=', None),
            # TODO: template = product_template
            ('template_parent', '=', None),
            ], ondelete='CASCADE', depends=['sale'])
    template_childs = fields.One2Many('sale.line', 'template_parent', 'Childs',
        domain=[('type', '=', 'line')])

    @classmethod
    def __setup__(cls):
        super(SaleLine, cls).__setup__()
        if cls.type.states.get('readonly'):
            cls.type.states['readonly'] = Or(cls.type.states['readonly'],
                Bool(Eval('template_parent')),
                Bool(Eval('template_childs')))
        else:
            cls.type.states['readonly'] = Or(Bool(Eval('template_parent')),
                Bool(Eval('template_childs')))
        cls.type.depends += ['template_parent', 'template_childs']

        cls.product.states['invisible'] = Or(cls.product.states['invisible'],
            Bool(Eval('template', -1)))

        if 'template' not in cls.product.depends:
            readonly = Or(Bool(Eval('template', -1)),
                       Bool(Eval('template_parent', -1)))
            if cls.product.states.get('reaonly'):
                readonly = Or(cls.product.states['readonly'], readonly)
            cls.product.states['readonly'] = readonly
            cls.product.depends += ['template', 'template_parent']

        cls.unit.states['required'] = Or(cls.unit.states['required'],
            Bool(Eval('template')))
        readonly = Bool(Eval('template_parent'))
        if cls.unit.states.get('readonly'):
            readonly = Or(cls.unit.states['readonly'], readonly)
        cls.unit.states['readonly'] = readonly
        cls.unit.depends += ['template', 'template_parent']

        readonly = Bool(Eval('template', 0))
        if cls.quantity.states.get('readonly'):
            readonly = Or(cls.quantity.states['readonly'], readonly)
        cls.quantity.states['readonly'] = readonly
        cls.quantity.depends.append('template')

        for fname in ('unit_price', 'amount', 'taxes'):
            field = getattr(cls, fname)
            if field.states.get('readonly'):
                field.states['readonly'] = Or(field.states['readonly'],
                    Bool(Eval('template_parent', 0)))
            else:
                field.states['readonly'] = Bool(Eval('template_parent', 0))
            field.depends.append('template_parent')

        cls._buttons.update({
                'set_quantities_wizard': {
                    'invisible': ~Bool(Eval('template')),
                    'readonly': Eval('_parent_sale', {}).get('state',
                        '') != 'draft',
                    },
                })

    @fields.depends('template', 'quantity', 'unit', 'description', 'sale',
        '_parent_sale.party')
    def on_change_template(self):
        Template = Pool().get('product.template')

        if not self.template:
            return

        party = None
        party_context = {}
        if self.sale and self.sale.party:
            party = self.sale.party
            if party.lang:
                party_context['language'] = party.lang.code

        self.quantity = 0

        category = self.template.sale_uom.category
        if not self.unit or self.unit not in category.uoms:
            self.unit = self.template.sale_uom

        # Set taxes before unit_price to have taxes in context of sale price
        taxes = []
        pattern = self._get_tax_rule_pattern()
        for tax in self.template.customer_taxes_used:
            if party and party.customer_tax_rule:
                tax_ids = party.customer_tax_rule.apply(tax, pattern)
                if tax_ids:
                    taxes.extend(tax_ids)
                continue
            taxes.append(tax.id)
        if party and party.customer_tax_rule:
            tax_ids = party.customer_tax_rule.apply(None, pattern)
            if tax_ids:
                taxes.extend(tax_ids)
        self.taxes = taxes

        with Transaction().set_context(self._get_context_sale_price()):
            self.unit_price = Template.get_sale_price([self.template],
                0)[self.template.id]
            if self.unit_price:
                self.unit_price = self.unit_price.quantize(
                    Decimal(1) / 10 ** self.__class__.unit_price.digits[1])

        if not self.description:
            with Transaction().set_context(party_context):
                self.description = Template(self.template.id).rec_name

    @fields.depends('template', 'template_parent')
    def on_change_quantity(self):
        Template = Pool().get('product.template')

        super(SaleLine, self).on_change_quantity()

        if self.template_parent:
            self.unit_price = Decimal('0.0')
        elif self.template:
            with Transaction().set_context(
                    self._get_context_sale_price()):
                self.unit_price = Template.get_sale_price([self.template],
                    self.quantity or 0)[self.template.id]
                if self.unit_price:
                    self.unit_price = self.unit_price.quantize(
                        Decimal(1) / 10 ** self.__class__.unit_price.digits[1])

    def get_invoice_line(self):
        if self.template_parent:
            return []

        invoice_lines = super(SaleLine, self).get_invoice_line()
        for inv_line in invoice_lines:
            inv_line.sequence = self.sequence
        return invoice_lines

    @classmethod
    @ModelView.button_action(
        'sale_pos_template_quantities.wizard_set_quantities')
    def set_quantities_wizard(cls, lines):
        pass

    def update_template_line_quantity(self):
        if not self.template_childs:
            return

        old_unit_price = self.unit_price
        if (self.on_change_quantity().unit_price == old_unit_price):
            # The user didn't changed the unit price
            old_unit_price = None

        self.quantity = sum(l.quantity for l in self.template_childs)
        self.on_change_quantity()

        if old_unit_price is not None:
            self.unit_price = old_unit_price

    def update_sequence(self, next_sequence):
        if self.template_parent:
            return next_sequence
        if self.sequence != next_sequence:
            self.sequence = next_sequence
            self.save()
        next_sequence += 1
        return self.update_child_lines_sequence(next_sequence)

    def update_child_lines_sequence(self, next_sequence):
        for child_line in self.template_childs:
            if child_line.sequence != next_sequence:
                child_line.sequence = next_sequence
                child_line.save()
            next_sequence += 1
        return next_sequence

    @classmethod
    def create(cls, vlist):
        template_lines_to_update = set()
        if not Transaction().context.get('no_update_template_qty'):
            for vals in vlist:
                if vals.get('template_parent'):
                    template_lines_to_update.add(vals['template_parent'])
        new_lines = super(SaleLine, cls).create(vlist)
        if template_lines_to_update:
            for template_line in cls.browse(list(template_lines_to_update)):
                template_line.update_template_line_quantity()
                template_line.save()
        return new_lines

    @classmethod
    def copy(cls, lines, default=None):
        if default is None:
            default = {}
        else:
            default = default.copy()
        default['template_childs'] = None
        with Transaction().set_context(no_update_template_qty=True):
            new_lines = super(SaleLine, cls).copy(lines, default=default)

        lines = sorted(lines, key=lambda a: (a.template, a.product))
        new_lines = sorted(new_lines, key=lambda a: (a.template, a.product))
        new_line_by_line = dict((l, nl) for l, nl in zip(lines, new_lines))
        for new_line in new_lines:
            parent_line = new_line.template_parent
            if parent_line and parent_line in lines:
                new_line.template_parent = new_line_by_line[parent_line]
                new_line.save()
        return new_lines

    @classmethod
    def write(cls, *args):
        template_lines_to_update = set()
        actions = iter(args)
        for lines, vals in zip(actions, actions):
            if not Transaction().context.get('no_update_template_qty'):
                if vals.get('template_parent'):
                    template_lines_to_update.add(vals['template_parent'])
                if vals.get('template_childs'):
                    template_lines_to_update |= set(l.id for l in lines)
                if 'quantity' in vals:
                    for line in lines:
                        if line.template_parent:
                            template_lines_to_update.add(
                                line.template_parent.id)
        super(SaleLine, cls).write(*args)
        if template_lines_to_update:
            for template_line in cls.browse(list(template_lines_to_update)):
                template_line.update_template_line_quantity()
                template_line.save()

    @classmethod
    def delete(cls, lines):
        template_lines_to_update = set()
        if not Transaction().context.get('no_update_template_qty'):
            for line in lines:
                if line.template_parent:
                    template_lines_to_update.add(line.template_parent.id)
        super(SaleLine, cls).delete(lines)
        if template_lines_to_update:
            for template_line in cls.browse(list(template_lines_to_update)):
                template_line.update_template_line_quantity()
                template_line.save()


class SetQuantitiesStart(ModelView):
    '''Set Quantities Wizard'''
    __name__ = 'sale_pos.set_quantities.start'

    template_line = fields.Many2One('sale.line', 'Template Line', domain=[
            ('type', '=', 'template'),
            ])
    lines = fields.One2Many('sale_pos.set_quantities.start.line', 'start',
        'Quantities', size=Eval('n_lines', 0), depends=['n_lines'])
    n_lines = fields.Integer('Quantities')
    total_quantity = fields.Float('Total Quantity',
        digits=(16, Eval('unit_digits', 2)), readonly=True,
        depends=['unit_digits'])
    unit_digits = fields.Integer('Unit Digits')

    @fields.depends('lines')
    def on_change_with_total_quantity(self):
        quantity = 0.0
        for line in self.lines:
            for fname in dir(line):
                if (not fname.startswith('attribute_value_y') or
                        fname == 'attribute_value_y'):
                    continue
                quantity += getattr(line, fname) or 0.0
        return quantity


class SetQuantitiesStartLine(ModelView):
    '''Set Quantities Wizard Start Line'''
    __name__ = 'sale_pos.set_quantities.start.line'

    start = fields.Many2One('sale_pos.set_quantities.start', 'Start',
       required=True)
    attribute_value_x = fields.Many2One('product.attribute.value', 'Value',
        required=True, readonly=True)
    attribute_value_y = fields.Float('Quantity',
        digits=(16, Eval('unit_digits', 2)), depends=['unit_digits'])
    total = fields.Float('Total', digits=(16, Eval('unit_digits', 2)),
        readonly=True, depends=['unit_digits'])
    unit_digits = fields.Integer('Unit Digits')

    @fields.depends('attribute_value_y')
    def on_change_with_total(self):
        total_quantity = 0.0
        for fname in dir(self):
            if (not fname.startswith('attribute_value_y') or
                    fname == 'attribute_value_y'):
                continue
            total_quantity += getattr(self, fname) or 0.0
        return total_quantity

    @classmethod
    def _view_look_dom_arch(cls, tree, type_, field_children=None):
        pool = Pool()
        SaleLine = pool.get('sale.line')

        res = tree.xpath('//field[@name=\'attribute_value_x\']')
        if not res:
            return

        template_line = SaleLine(Transaction().context.get('active_id'))
        if template_line and template_line.id:
            attr_value_y_list = template_line.template.get_y_attribute_values()

            element_value_x = res[0]
            new_elements = []
            for attribute_value in attr_value_y_list:
                new_element = copy.copy(element_value_x)
                new_element.set('name', 'attribute_value_y' +
                    str(attribute_value.id))
                new_element.set('sum', attribute_value.rec_name)
                new_elements.append(new_element)

            parent = element_value_x.getparent()
            base_index = parent.index(element_value_x)
            for i, element in enumerate(new_elements, 1):
                parent.insert(base_index + i, element)

        return super(SetQuantitiesStartLine, cls)._view_look_dom_arch(tree,
            type_, field_children=field_children)

    @classmethod
    def fields_get(cls, fields_names=None):
        pool = Pool()
        SaleLine = pool.get('sale.line')

        res = super(SetQuantitiesStartLine, cls).fields_get(fields_names)

        # prevent sort clicking in column header
        for field_values in list(res.values()):
            field_values['sortable'] = False

        template_line = SaleLine(Transaction().context.get('active_id'))
        if not template_line.id:
            return res

        if template_line and template_line.id:
            attr_value_y_field = super(SetQuantitiesStartLine, cls).fields_get(
                        ['attribute_value_y'])['attribute_value_y']
            attr_value_y_field['sortable'] = False

            attr_value_y_list = template_line.template.get_y_attribute_values()
            encoder = PYSONEncoder()
            y_field_names = []
            for attribute_value in attr_value_y_list:
                name = 'attribute_value_y' + str(attribute_value.id)
                if True or name in fields_names or not fields_names:
                    y_field_names.append(name)
                    res[name] = attr_value_y_field.copy()
                    res[name]['states'] = encoder.encode({
                            'readonly': And(~Bool(Eval(name, 0)),
                                Eval(name, -1) != 0),
                            })
                    res[name]['string'] = (' ' * 12) + attribute_value.rec_name
            if 'total' in fields_names:
                res['total']['on_change_with'] = y_field_names
        return res


class SetQuantities(Wizard):
    '''Set Quantities Wizard'''
    __name__ = 'sale_pos.set_quantities'

    start = StateView('sale_pos.set_quantities.start',
        'sale_pos_template_quantities.set_quantities_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Set', 'set_', 'tryton-ok', default=True),
        ])
    set_ = StateTransition()
    update_sequences_ = StateTransition()

    def default_start(self, fields):
        SaleLine = Pool().get('sale.line')

        template_line = SaleLine(Transaction().context.get('active_id'))
        if not template_line or not template_line.id:
            return {}
        # Raw products can be managed creating a field called raw_products
        # into the SetQuantitiesStart model.
        raw_products = self.start._values.get('raw_products', False)
        product_by_attributes = template_line.template.product_by_attributes(
            raw_products=raw_products)
        child_line_by_product = dict((l.product, l)
            for l in template_line.template_childs)

        lines_vlist = []
        total_quantity = 0.0
        for attr_value_x in template_line.template.get_x_attribute_values():
            y_values = product_by_attributes[attr_value_x]
            line_vals = {
                'attribute_value_x': attr_value_x.id,
                'attribute_value_x.rec_name': attr_value_x.rec_name,
                'unit_digits': template_line.unit.digits,
                }
            line_total_quantity = 0.0
            for attr_value_y, product in list(y_values.items()):
                quantity = 0
                if product in child_line_by_product:
                    quantity = child_line_by_product[product].quantity
                line_vals['attribute_value_y%d' % attr_value_y.id] = quantity
                line_total_quantity += quantity
            line_vals['total'] = line_total_quantity
            total_quantity += line_total_quantity
            lines_vlist.append(line_vals)
        return {
            'template_line': template_line.id,
            'template_line.rec_name': template_line.rec_name,
            'lines': lines_vlist,
            'n_lines': len(lines_vlist),
            'total_quantity': total_quantity,
            'unit_digits': template_line.unit.digits,
            }

    def transition_set_(self, *args, **kwargs):
        pool = Pool()
        AttributeValue = pool.get('product.attribute.value')
        SaleLine = pool.get('sale.line')
        template_line = self.start.template_line
        product_by_attributes = template_line.template.product_by_attributes(
            raw_products=kwargs.get('raw_products', False))
        child_line_by_product = dict((l.product, l)
            for l in template_line.template_childs)

        lines_to_delete = []
        for quantity_line in self.start.lines:
            value_x = quantity_line.attribute_value_x
            for fname in dir(quantity_line):
                if (not fname.startswith('attribute_value_y') or
                        fname == 'attribute_value_y'):
                    continue
                attribute_value_id = int(fname[17:])
                value_y = AttributeValue(attribute_value_id)

                if value_y not in product_by_attributes[value_x]:
                    continue

                product = product_by_attributes[value_x][value_y]
                line = child_line_by_product.get(product)

                quantity = getattr(quantity_line, fname)
                if not quantity:
                    if line:
                        lines_to_delete.append(line)
                    continue

                if not line:
                    line = SaleLine()
                    line.sequence = template_line.sequence
                    line.template_parent = template_line
                    line.product = product
                    line.unit = template_line.unit
                    line.description = None
                    line.sale = template_line.sale
                    line.quantity = quantity
                    line.unit_price = Decimal('0.0')
                    line.on_change_product()

                line.quantity = quantity
                line.unit_price = Decimal('0.0')
                with Transaction().set_context(no_update_template_qty=True):
                    line.save()

        old_unit_price = template_line.unit_price
        template_line.on_change_quantity()
        if template_line.unit_price == old_unit_price:
            # The user didn't changed the unit price
            old_unit_price = None

        template_line.quantity = self.start.total_quantity
        template_line.on_change_quantity()
        if old_unit_price is not None:
            template_line.unit_price = old_unit_price

        with Transaction().set_context(no_update_template_qty=True):
            template_line.save()
            if lines_to_delete:
                SaleLine.delete(lines_to_delete)
        return 'update_sequences_'

    def transition_update_sequences_(self):
        pool = Pool()
        Sale = pool.get('sale.sale')

        next_sequence = 1
        for sale_line in Sale(self.start.template_line.sale.id).lines:
            if not sale_line.template_parent:
                next_sequence = sale_line.update_sequence(next_sequence)
        return 'end'
