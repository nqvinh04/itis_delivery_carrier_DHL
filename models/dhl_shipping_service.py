from odoo import api, fields, models

LABEL_FORMAT_TYPE = [
    ('8X4_A4_PDF', '8X4_A4_PDF'),
    ('8X4_thermal', '8X4_thermal'),
    ('8X4_A4_TC_PDF', '8X4_A4_TC_PDF'),
    ('6X4_thermal', '6X4_thermal'),
    ('6X4_A4_PDF', '6X4_A4_PDF'),
    ('8X4_CI_PDF', '8X4_CI_PDF'),
    ('8X4_CI_thermal', '8X4_CI_thermal'),
    ('8X4_RU_A4_PDF', '8X4_RU_A4_PDF'),
    ('6X4_PDF', '6X4_PDF'),
    ('8X4_PDF', '8X4_PDF'),
    ('8X4_CustBarCode_PDF', '8X4_CustBarCode_PDF'),
    ('8X4_CustBarCode_thermal', '8X4_CustBarCode_thermal'),
]


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    delivery_type = fields.Selection(selection_add=[('dhl', 'DHL')], ondelete={'dhl': 'cascade'})
    dhl_service_id = fields.Many2one('delivery.carrier.dhl.service', string='DHL Service')
    dhl_drop_off_id = fields.Many2one('delivery.carrier.dhl.drop.off', string='DHL Drop-Off Type')
    dhl_site_id = fields.Char(string='Site ID')
    dhl_account_no = fields.Char(string='DHL Account Number')
    dhl_password = fields.Char(string='DHL Password')
    dhl_label_format = fields.Selection(selection=[('pdf', 'PDF'), ('zpl2', 'ZPL2'), ('epl2', 'EPL2')],
                                        string="DHL Label Format", required='1', default="pdf")
    dhl_label_type = fields.Selection(selection=LABEL_FORMAT_TYPE, string="DHL Label Type", default="8X4_A4_PDF")
    exporter_code = fields.Char(string="Exporter Code")
    declaration_text1 = fields.Char(string="Declaration Text 1")
    declaration_text2 = fields.Char(string="Declaration Text 2")
    declaration_text3 = fields.Char(string="Declaration Text 3")


class WKShippingDhlDropOff(models.Model):
    _name = "delivery.carrier.dhl.drop.off"
    _description = "Delivery Carrier DHL Drop Off"

    name = fields.Char(string="Name", required=1)
    code = fields.Char(string="Code", required=1)


class WKShippingDhlService(models.Model):
    _name = "delivery.carrier.dhl.service"
    _description = "Delivery Carrier DHL Service"

    name = fields.Char(string="Name", required=1)
    global_code = fields.Char(string="Global Product Code", required=1)
    local_code = fields.Char(string="Local Product Code", required=1)
    term_of_trade = fields.Char(string="Terms Of Trade", required=1, default='DDU')
    is_dutiable = fields.Selection(selection=[('no', 'No'), ('yes', 'Yes')], string='IS Dutiable', required=1,
                                   default='no')
    is_insured = fields.Selection(selection=[('no', 'No'), ('yes', 'Yes')], string='IS Insured',
                                  required=1, default='no')


class ProductPackage(models.Model):
    _inherit = 'product.package'

    delivery_type = fields.Selection(selection_add=[('dhl', 'DHL')])


class ProductPackaging(models.Model):
    _inherit = 'product.packaging'

    package_carrier_type = fields.Selection(selection_add=[('dhl', 'DHL')])

    ready_time_dhl = fields.Integer(string="Ready Time", required=1, default=10,
                                    help='Package Ready Time after order submission(in hours)')
