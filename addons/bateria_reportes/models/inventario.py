from odoo import models, fields, api
#from odoo.exceptions import UserError

# =================================================================================
# 1. UBICACIONES FÍSICAS (Actualizado a Jerarquía Padre/Hijo)
# =================================================================================

# Esta es una prueba para actualizar el commit y los archivos junto con el git.ignore

# =================================================================================
# 2. EL INVENTARIO CENTRAL
# =================================================================================
class BateriaInventario(models.Model):
    _name = 'bateria.inventario'
    _description = 'Movimientos de Inventario'
    _order = 'fecha desc'

    fecha = fields.Datetime(default=fields.Datetime.now, required=True)
    
    #tipo_movimiento = fields.Selection([
     #   ('entrada', 'Entrada (Carga)'), 
      #  ('salida', 'Salida (Venta/Traslado)')], 
       # required=True)
    
    #producto_id = fields.Many2one('bateria.producto', string='Modelo Batería', required=True)
    #cantidad = fields.Integer(required=True, default=1)
    
    # AHORA EL INVENTARIO ESTÁ CONECTADO A LUGARES REALES
    # ubicacion_id = fields.Many2one('bateria.ubicacion', string='Ubicación Física', required=True)
    
    # stock_disponible = fields.Integer(related='producto_id.stock_actual', readonly=True)
    
    # fecha_vencimiento = fields.Date(string='Fecha de Vencimiento', readonly=True)
    
    #nota = fields.Char()
    #orden_venta_id = fields.Many2one('bateria.orden.venta')
