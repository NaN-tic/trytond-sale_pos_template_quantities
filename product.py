# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from collections import defaultdict
from operator import attrgetter

from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction

__all__ = ['Template']


class Template(metaclass=PoolMeta):
    __name__ = 'product.template'

    @staticmethod
    def get_sale_price(templates, quantity=0):
        '''
        Return the sale price for templates and quantity.
        It uses if exists from the context:
            uom: the unit of measure
            currency: the currency id for the returned price
        '''
        pool = Pool()
        Uom = pool.get('product.uom')
        User = pool.get('res.user')
        Currency = pool.get('currency.currency')
        Date = pool.get('ir.date')
        Party = pool.get('party.party')
        PriceList = pool.get('product.price_list')

        today = Date.today()
        prices = {}

        uom = None
        if Transaction().context.get('uom'):
            uom = Uom(Transaction().context.get('uom'))

        currency = None
        if Transaction().context.get('currency'):
            currency = Currency(Transaction().context.get('currency'))

        price_list = None
        if (Transaction().context.get('price_list')
                and Transaction().context.get('customer')):
            price_list = PriceList(Transaction().context['price_list'])
            customer = Party(Transaction().context['customer'])

        user = User(Transaction().user)

        for template in templates:
            prices[template.id] = template.list_price
            if uom:
                prices[template.id] = Uom.compute_price(
                    template.default_uom, prices[template.id], uom)
            if currency and user.company:
                if user.company.currency != currency:
                    date = Transaction().context.get('sale_date') or today
                    with Transaction().set_context(date=date):
                        prices[template.id] = Currency.compute(
                            user.company.currency, prices[template.id],
                            currency, round=False)
            if price_list:
                price_list_category = (template.price_list_category and
                    template.price_list_category.id or None)
                prices[template.id] = price_list.compute(customer, None,
                    prices[template.id], quantity,
                    uom or template.default_uom, pattern={
                        'price_list_category': price_list_category,
                        })
        return prices

    def product_by_attributes(self, raw_products=False):
        """
        Return a not completted matrix (dictionary of defaultdict) with
        X Attribute Values as keys for first level, Y Attribute Values as key
        for second level, and the product with these two attributes as value.
        If the template doesn't have variants for some combination of X/Y
        attribute values it doesn't add this
        ;param raw_products: provide compatibility awith product_raw_variant
            module and its dependants.
            If this module is installed, it returns main variants despite this
            param is true
        """
        if not self or not self.id:
            return {}
        product_by_attributes = defaultdict(dict)
        for product in self.products:
            if hasattr(product, 'is_raw_product'):
                if raw_products and not product.is_raw_product:
                    continue
                elif not raw_products and product.is_raw_product:
                    continue
            value_x = value_y = None
            for attribute_value in product.attribute_values:
                # TODO: better attribute selection
                if attribute_value.attribute.code.startswith('colors'):
                    value_x = attribute_value
                elif attribute_value.attribute.code.startswith('sizes'):
                    value_y = attribute_value
                if value_x and value_y:
                    break
            if value_x is None or value_y is None:
                continue
            product_by_attributes[value_x][value_y] = product
        return product_by_attributes

    def get_x_attribute_values(self):
        """
        Return an ordered list of values of attribute to be used in X absis
        that exists some Template's product with this value.
        """
        x_attribute_values = set(attr_v for p in self.products
            for attr_v in p.attribute_values
            if attr_v.attribute.code.startswith('colors'))  # TODO
        return sorted(x_attribute_values, key=attrgetter('sequence'))

    def get_y_attribute_values(self):
        """
        Return an ordered list of values of attribute to be used in Y absis
        that exists some Template's product with this value.
        """
        y_attribute_values = set(attr_v for p in self.products
            for attr_v in p.attribute_values
            if attr_v.attribute.code.startswith('sizes'))  # TODO
        return sorted(y_attribute_values, key=attrgetter('sequence'))
