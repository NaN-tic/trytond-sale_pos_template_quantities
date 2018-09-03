# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from . import product
from . import sale


def register():
    Pool.register(
        product.Template,
        sale.Sale,
        sale.SaleLine,
        sale.SetQuantitiesStart,
        sale.SetQuantitiesStartLine,
        module='sale_pos_template_quantities', type_='model')
    Pool.register(
        sale.SetQuantities,
        module='sale_pos_template_quantities', type_='wizard')
