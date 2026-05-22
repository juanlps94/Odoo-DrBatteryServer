from odoo import models, fields

class TablaDinamicaAnalisisVentas(models.Model):
    _name = 'bateria.tabla.dinamica.ventas'
    _description = 'Tabla Dinámica Análisis de Ventas'
    _order = 'mes'

    mes = fields.Char(string='Mes', required=True)
    total_ventas = fields.Float(string='Total Ventas')
    total_punto_venta = fields.Float(string='Total Punto de Venta')
    total_imponible = fields.Float(string='Total Imponible')
