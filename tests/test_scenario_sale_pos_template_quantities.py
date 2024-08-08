import unittest
from decimal import Decimal

from proteus import Model
from trytond.modules.account.tests.tools import (create_chart,
                                                 create_fiscalyear, create_tax,
                                                 get_accounts)
from trytond.modules.account_invoice.tests.tools import (
    create_payment_term, set_fiscalyear_invoice_sequences)
from trytond.modules.company.tests.tools import create_company, get_company
from trytond.modules.product_variant.tests.tools import create_attributes
from trytond.modules.sale_shop.tests.tools import create_shop
from trytond.tests.test_tryton import drop_db
from trytond.tests.tools import activate_modules, set_user


class Test(unittest.TestCase):

    def setUp(self):
        drop_db()
        super().setUp()

    def tearDown(self):
        drop_db()
        super().tearDown()

    def test(self):

        # Install account_invoice
        config = activate_modules('sale_pos_template_quantities')

        # Create company
        _ = create_company()
        company = get_company()

        # Reload the context
        User = Model.get('res.user')
        config._context = User.get_preferences(True, config.context)

        # Create fiscal year
        fiscalyear = set_fiscalyear_invoice_sequences(
            create_fiscalyear(company))
        fiscalyear.click('create_period')

        # Create chart of accounts
        _ = create_chart(company)
        accounts = get_accounts(company)
        revenue = accounts['revenue']
        expense = accounts['expense']

        # Create tax
        tax = create_tax(Decimal('.10'))
        tax.save()

        # Create parties
        Party = Model.get('party.party')
        customer = Party(name='Customer')
        customer.save()

        # Create attributes
        Attribute = Model.get('product.attribute')
        attributes = create_attributes()

        # Create account category
        ProductCategory = Model.get('product.category')
        account_category = ProductCategory(name="Account Category")
        account_category.accounting = True
        account_category.account_expense = expense
        account_category.account_revenue = revenue
        account_category.customer_taxes.append(tax)
        account_category.save()

        # Create product
        ProductUom = Model.get('product.uom')
        unit, = ProductUom.find([('name', '=', 'Unit')])
        ProductTemplate = Model.get('product.template')
        template = ProductTemplate()
        template.name = 'product'
        template.default_uom = unit
        template.type = 'goods'
        template.salable = True
        template.list_price = Decimal('10')
        template.cost_price_method = 'fixed'
        template.account_category = account_category
        attributes = Attribute.find()

        for attribute in attributes:
            template.attributes.append(attribute)

        template.save()
        ProductTemplate.generate_variants([template.id], config.context)

        # Create payment term
        payment_term = create_payment_term()
        payment_term.save()

        # Create Product Price List
        ProductPriceList = Model.get('product.price_list')
        product_price_list = ProductPriceList()
        product_price_list.name = 'Price List'
        product_price_list.company = company
        product_price_list.save()

        # Create Sale Shop
        shop = create_shop(payment_term, product_price_list)
        shop.save()

        # Save Sale Shop User
        User = Model.get('res.user')
        user, = User.find([])
        user.shops.append(shop)
        user.shop = shop
        user.save()
        set_user(user)

        # Create a sale
        Sale = Model.get('sale.sale')
        sale = Sale()
        sale.party = customer
        sale.payment_term = payment_term
        sale_line = sale.lines.new()
        sale_line.template = template
        sale.save()
        sale.reload()
