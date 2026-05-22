from odoo import models, fields

class ModeloBateria(models.Model):
    _name = 'bateria.modelo'
    _description = 'Modelo de Batería'
    
    name = fields.Char(string='Nombre del Modelo', required=True)
    codigo = fields.Char(string='Código', required=True, size=20)
    voltaje = fields.Float(string='Voltaje (V)', required=True)
    capacidad = fields.Float(string='Capacidad (Ah)', required=True)
    precio_venta_bs = fields.Float(string='Precio Venta Bs', required=True)
    stock_actual = fields.Integer(string='Stock Actual', default=0)
    activo = fields.Boolean(string='Activo', default=True)