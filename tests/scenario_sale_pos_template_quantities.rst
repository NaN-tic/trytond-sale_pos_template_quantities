=====================================
Sale POS Template Quantities Scenario
=====================================

Imports::

    >>> import datetime
    >>> from dateutil.relativedelta import relativedelta
    >>> from decimal import Decimal
    >>> from operator import attrgetter
    >>> from proteus import config, Model, Wizard
    >>> from trytond.tests.tools import activate_modules
    >>> from trytond.modules.company.tests.tools import create_company, \
    ...     get_company
    >>> from trytond.modules.account.tests.tools import create_fiscalyear, \
    ...     create_chart, get_accounts, create_tax
    >>> from trytond.modules.account_invoice.tests.tools import \
    ...     set_fiscalyear_invoice_sequences, create_payment_term
    >>> from trytond.modules.product_variant.tests.tools import create_attributes
    >>> today = datetime.date.today()

Install account_invoice::

    >>> config = activate_modules('sale_pos_template_quantities')

Create company::

    >>> _ = create_company()
    >>> company = get_company()

Reload the context::

    >>> User = Model.get('res.user')
    >>> Group = Model.get('res.group')
    >>> config._context = User.get_preferences(True, config.context)

Create fiscal year::

    >>> fiscalyear = set_fiscalyear_invoice_sequences(
    ...     create_fiscalyear(company))
    >>> fiscalyear.click('create_period')

Create chart of accounts::

    >>> _ = create_chart(company)
    >>> accounts = get_accounts(company)
    >>> revenue = accounts['revenue']
    >>> expense = accounts['expense']
    >>> cash = accounts['cash']

    >>> Journal = Model.get('account.journal')
    >>> cash_journal, = Journal.find([('type', '=', 'cash')])
    >>> cash_journal.credit_account = cash
    >>> cash_journal.debit_account = cash
    >>> cash_journal.save()

Create tax::

    >>> tax = create_tax(Decimal('.10'))
    >>> tax.save()

Create parties::

    >>> Party = Model.get('party.party')
    >>> customer = Party(name='Customer')
    >>> customer.save()

Create attributes::

    >>> Attribute = Model.get('product.attribute')
    >>> attributes = create_attributes()

Create account category::

    >>> ProductCategory = Model.get('product.category')
    >>> account_category = ProductCategory(name="Account Category")
    >>> account_category.accounting = True
    >>> account_category.account_expense = expense
    >>> account_category.account_revenue = revenue
    >>> account_category.customer_taxes.append(tax)
    >>> account_category.save()

Create product::

    >>> ProductUom = Model.get('product.uom')
    >>> unit, = ProductUom.find([('name', '=', 'Unit')])
    >>> ProductTemplate = Model.get('product.template')
    >>> template = ProductTemplate()
    >>> template.name = 'product'
    >>> template.default_uom = unit
    >>> template.type = 'goods'
    >>> template.purchasable = True
    >>> template.salable = True
    >>> template.list_price = Decimal('10')
    >>> template.cost_price_method = 'fixed'
    >>> template.account_category = account_category
    >>> attributes = Attribute.find()
    >>> for attribute in attributes:
    ...     template.attributes.append(attribute)
    >>> template.save()
    >>> ProductTemplate.generate_variants([template.id], config.context)

Create payment term::

    >>> payment_term = create_payment_term()
    >>> payment_term.save()

Create Product Price List::

    >>> ProductPriceList = Model.get('product.price_list')
    >>> product_price_list = ProductPriceList()
    >>> product_price_list.name = 'Price List'
    >>> product_price_list.company = company
    >>> product_price_list.save()

Create a shop::

    >>> Shop = Model.get('sale.shop')
    >>> Sequence = Model.get('ir.sequence')
    >>> Location = Model.get('stock.location')
    >>> shop = Shop()
    >>> shop.name = 'Shop'
    >>> warehouse, = Location.find([
    ...         ('type', '=', 'warehouse'),
    ...         ])
    >>> shop.warehouse = warehouse
    >>> shop.price_list = product_price_list
    >>> shop.payment_term = payment_term
    >>> sequence, = Sequence.find([
    ...         ('code', '=', 'sale.sale'),
    ...         ])
    >>> shop.sale_sequence = sequence
    >>> shop.sale_invoice_method = 'shipment'
    >>> shop.sale_shipment_method = 'order'
    >>> shop.save()

Save Sale Shop User::

    >>> user, = User.find([])
    >>> user.shops.append(shop)
    >>> user.shop = shop
    >>> user.save()

Create a sale::

    >>> Sale = Model.get('sale.sale')
    >>> SaleLine = Model.get('sale.line')
    >>> sale = Sale()
    >>> sale.party = customer
    >>> sale.payment_term = payment_term
    >>> sale_line = sale.lines.new()
    >>> sale_line.template = template
    >>> sale.save()
    >>> sale.reload()
    >>> line_template = sale.lines[0]
    >>> # set_quantity = Wizard('sale_pos.set_quantities', [line_template])
    >>> # TODO *** KeyError: 'attribute_value_y4'

