from odoo import models, fields

class AnalisisVentas(models.Model):
    _name = 'bateria.analisis.ventas'
    _description = 'Informe de Análisis de Ventas'
    _order = 'fecha_entrega desc'

    fecha_entrega = fields.Datetime(
        string='Fecha entrega',
        required=True
    )

    pedido_numero = fields.Char(
        string='Pedido Nº',
        required=True
    )

    comercial = fields.Char(
        string='Comercial'
    )

    equipo_ventas = fields.Char(
        string='Equipo de ventas'
    )

    compania = fields.Char(
        string='Compañía'
    )

    total = fields.Float(
        string='Total'
    )
