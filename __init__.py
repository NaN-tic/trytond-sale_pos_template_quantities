# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from .product import *
from .sale import *


def register():
    Pool.register(
        Template,
        Sale,
        SaleLine,
        SetQuantitiesStart,
        SetQuantitiesStartLine,
        module='sale_pos_template_quantities', type_='model')
    Pool.register(
        SetQuantities,
        module='sale_pos_template_quantities', type_='wizard')
