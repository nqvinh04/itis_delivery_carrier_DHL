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
        'views/dhl_delivery_carrier.xml',
        'views/dhl_delivery_carrier.xml',
        'views/res_config.xml',
    ],
    "demo": ['data/demo.xml'],
    "images": ['static/description/Banner.png'],
    "application": True,
    "installable": True,
    "pre_init_hook": "pre_init_check",
    "external_dependencies": {'python': ['urllib3']},
}
