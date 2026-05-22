from odoo import models, fields

class BateriaTallerArticulo(models.Model):
    _name = 'bateria.taller.articulo'
    _description = 'Artículos de Taller (Lista Dr. Battery)'

    codigo = fields.Char(string='Artículo (Código)', required=True)
    gama = fields.Selection([('automovil', 'Automóvil'), ('motocicleta', 'Motocicleta')], string='Gama', required=True)
    name = fields.Char(string='Descripción', required=True)
    unidades_caja = fields.Integer(string='Caja (Unidades)')
    presentacion = fields.Char(string='Pres. (Tamaño)')
    pvp_detal_taller = fields.Float(string='PVP Detal / Taller ($)')
    pvp_instituciones = fields.Float(string='PVP Instituciones ($)')