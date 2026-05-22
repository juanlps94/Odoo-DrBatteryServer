from odoo import models, fields

class CierreCaja(models.Model):
    _name = 'bateria.cierre.caja'
    _description = 'Cierre de Caja'
    _rec_name = 'name'

    name = fields.Char(
        string='Referencia',
        required=True
    )

    fecha = fields.Date(
        string='Fecha',
        default=fields.Date.today,
        required=True
    )

    efectivo_usd = fields.Float(
        string='Efectivo USD'
    )

    efectivo_bs = fields.Float(
        string='Efectivo Bs'
    )

    transferencia = fields.Float(
        string='Transferencias'
    )

    total = fields.Float(
        string='Total',
        compute='_compute_total',
        store=True
    )

    observaciones = fields.Text(
        string='Observaciones'
    )

    def _compute_total(self):
        for rec in self:
            rec.total = (
                rec.efectivo_usd +
                rec.efectivo_bs +
                rec.transferencia
            )
