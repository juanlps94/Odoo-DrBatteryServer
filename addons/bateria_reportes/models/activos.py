from odoo import models, fields

class BateriaActivo(models.Model):
    _name = 'bateria.activo'
    _description = 'Inventario de Activos de la Empresa'

    name = fields.Char(string='Nombre del Activo', required=True)
    categoria = fields.Selection([
        ('equipos', 'Equipos y Maquinaria'), 
        ('muebles', 'Mobiliario'), 
        ('tecnologia', 'Tecnología'), 
        ('vehiculos', 'Vehículos'),
        ('otros', 'Otros')
    ], string='Categoría', default='equipos')
    fecha_adquisicion = fields.Date(string='Fecha de Adquisición', default=fields.Date.today)
    valor_compra = fields.Float(string='Valor de Compra ($)')
    compra_id = fields.Many2one('bateria.compra', string='Cuenta por Pagar Origen', readonly=True) # Cambia 'bateria.compra' por el nombre real de tu modelo
    estado = fields.Selection([
        ('operativo', 'Operativo'), 
        ('mantenimiento', 'En Mantenimiento'), 
        ('desincorporado', 'Desincorporado')
    ], default='operativo', string='Estado')