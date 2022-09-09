from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    module_itis_delivery_carrier_DHL = fields.Boolean(string="DHL Shipping Service")
