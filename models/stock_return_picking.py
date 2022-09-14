from odoo import api, models, fields


class ReturnPicking(models.TransientModel):
    _inherit = 'stock.return.picking'
    carrier_id = fields.Many2one('delivery.carrier', string="Delivery Method",
                                 domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
                                 help="Fill this field if you plan to invoice the shipping based on picking.")

    def _create_returns(self):
        # Prevent copy of the carrier and carrier price when generating return picking
        # (we have no integration of returns for now)
        new_picking, pick_type_id = super(ReturnPicking, self)._create_returns()
        picking = self.env['stock.picking'].browse(new_picking)
        picking.write({'carrier_id': self.carrier_id.id,
                       'delivery_type': self.carrier_id.delivery_type})
        return new_picking, pick_type_id
