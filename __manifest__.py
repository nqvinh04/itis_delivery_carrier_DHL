{
    "name": "Itis DHL Shipping Integration",
    "category": "Website",
    "version": "14.0.1.0.0",
    "description": """
            DHL Shipping API Integration as Odoo DHL Delivery Method .
            Provide Shipping Label Generation and Shipping Rate Calculator For Website as Well Odoo BackEnd.
    """,
    "depends": [
        'odoo_shipping_service_apps',
        'website_sale_delivery',
    ],
    "data": [
        'security/ir.model.access.csv',
        'data/data.xml',
        'data/package.xml',
        'data/delivery_demo.xml',
        'views/product_packaging_views.xml',
        'views/delivery_carrier_views.xml',
        'views/dhl_delivery_carrier.xml',
        'views/stock_return_picking_views.xml',
        'views/res_config.xml',
    ],
    "application": True,
    "installable": True,
    "external_dependencies": {'python': ['urllib3']},
}
