from odoo import models, fields, api
from odoo.exceptions import UserError

# =================================================================================
# 1. UBICACIONES FÍSICAS (Actualizado a Jerarquía Padre/Hijo)
# =================================================================================

class BateriaUbicacion(models.Model):
    _name = 'bateria.ubicacion'
    _description = 'Ubicaciones de Inventario'
    
    # Magia Odoo: El sistema mostrará la ruta completa en los menús (Ej: GDRB/Racksito)
    _rec_name = 'nombre_completo' 

    # VOLVEMOS A USAR 'name' PARA QUE NO DE ERROR EN LA ORDEN DE VENTA
    name = fields.Char(string='Nombre del Lugar', required=True, help="Ej: Racksito")
    ubicacion_padre_id = fields.Many2one('bateria.ubicacion', string='Ubicación padre', index=True)
    nombre_completo = fields.Char(string='Ruta Completa', compute='_compute_nombre_completo', store=True)

    tipo = fields.Selection([
        ('interna', 'Ubicación Interna'),
        ('cliente', 'Ubicación de Cliente'),
        ('perdida', 'Pérdida de Inventario (Chatarra)'),
        ('vista', 'Vista')
    ], string='Tipo de Ubicación', default='interna')
    
    compania = fields.Char(string='Compañía', default='Corporación de Servicios Múltiples Don Juan, C.A.')
    
    es_desecho = fields.Boolean(string='¿Es desecho?')
    es_devolucion = fields.Boolean(string='¿Es devolución?')

    @api.depends('name', 'ubicacion_padre_id.nombre_completo')
    def _compute_nombre_completo(self):
        for rec in self:
            if rec.ubicacion_padre_id:
                # Si tiene padre (Ej: GDRB), lo une con un "/"
                rec.nombre_completo = f"{rec.ubicacion_padre_id.nombre_completo}/{rec.name}"
            else:
                # Si no tiene padre (Es el almacén principal)
                rec.nombre_completo = rec.name

# =================================================================================
# 2. EL INVENTARIO CENTRAL
# =================================================================================
class BateriaInventario(models.Model):
    _name = 'bateria.inventario'
    _description = 'Movimientos de Inventario'
    _order = 'fecha desc'

    fecha = fields.Datetime(default=fields.Datetime.now, required=True)
    
    tipo_movimiento = fields.Selection([
        ('entrada', 'Entrada (Carga)'), 
        ('salida', 'Salida (Venta/Traslado)')], 
        required=True)
    
    producto_id = fields.Many2one('bateria.producto', string='Modelo Batería', required=True)
    cantidad = fields.Integer(required=True, default=1)
    
    # AHORA EL INVENTARIO ESTÁ CONECTADO A LUGARES REALES
    ubicacion_id = fields.Many2one('bateria.ubicacion', string='Ubicación Física', required=True)
    
    stock_disponible = fields.Integer(related='producto_id.stock_actual', readonly=True)
    
    fecha_vencimiento = fields.Date(string='Fecha de Vencimiento', readonly=True)
    
    nota = fields.Char()
    orden_venta_id = fields.Many2one('bateria.orden.venta')


# =================================================================================
# 3. MOTOR DE TRASLADOS (MOVIMIENTOS INTERNOS)
# =================================================================================
class BateriaTraslado(models.Model):
    _name = 'bateria.traslado'
    _description = 'Traslados de Baterías'

    name = fields.Char(string='Referencia', required=True, copy=False, default='Nuevo Traslado')
    fecha = fields.Datetime(string='Fecha', default=fields.Datetime.now)
    
    ubicacion_origen_id = fields.Many2one('bateria.ubicacion', string='Ubicación Origen', required=True)
    ubicacion_destino_id = fields.Many2one('bateria.ubicacion', string='Ubicación Destino', required=True)
    
    estado = fields.Selection([
        ('borrador', 'Borrador'),
        ('realizado', 'Realizado')
    ], string='Estado', default='borrador')

    linea_ids = fields.One2many('bateria.traslado.linea', 'traslado_id', string='Operaciones')
    nota = fields.Text(string='Nota / Info Adicional')

    def action_confirmar_traslado(self):
        inv_model = self.env['bateria.inventario']
        for traslado in self:
            for linea in traslado.linea_ids:
                # 1. VALIDACIONES DE SEGURIDAD
                if not linea.serial_ids:
                    raise UserError(f"Debes escanear o seleccionar los seriales para el modelo {linea.producto_id.nombre}.")
                if len(linea.serial_ids) != linea.cantidad:
                    raise UserError(f"Indicaste {linea.cantidad} unidades pero seleccionaste {len(linea.serial_ids)} seriales.")

                # 2. CAMBIAR FÍSICAMENTE EL SERIAL DE ALMACÉN
                for serial in linea.serial_ids:
                    serial.ubicacion_id = traslado.ubicacion_destino_id.id
                
                # Extraemos los seriales para guardarlos en el historial
                seriales_texto = ", ".join(linea.serial_ids.mapped('nombre'))

                # 3. SACAMOS LAS BATERÍAS DEL ORIGEN EN EL HISTORIAL
                inv_model.create({
                    'fecha': traslado.fecha,
                    'tipo_movimiento': 'salida',
                    'producto_id': linea.producto_id.id,
                    'cantidad': linea.cantidad,
                    'ubicacion_id': traslado.ubicacion_origen_id.id,
                    'nota': f'Traslado hacia {traslado.ubicacion_destino_id.nombre_completo} | Seriales: {seriales_texto}'
                })
                # 4. METEMOS LAS BATERÍAS EN EL DESTINO
                inv_model.create({
                    'fecha': traslado.fecha,
                    'tipo_movimiento': 'entrada',
                    'producto_id': linea.producto_id.id,
                    'cantidad': linea.cantidad,
                    'ubicacion_id': traslado.ubicacion_destino_id.id,
                    'nota': f'Traslado desde {traslado.ubicacion_origen_id.nombre_completo} | Seriales: {seriales_texto}'
                })
            traslado.estado = 'realizado'

class BateriaTrasladoLinea(models.Model):
    _name = 'bateria.traslado.linea'
    _description = 'Línea de Traslado'

    traslado_id = fields.Many2one('bateria.traslado', ondelete='cascade')
    producto_id = fields.Many2one('bateria.producto', string='Producto', required=True)
    cantidad = fields.Integer(string='Demanda', required=True, default=1)

    # 👇 NUEVO: CAMPO DE SERIALES (Solo muestra los seriales que están en el almacén de origen)
    serial_ids = fields.Many2many(
        'bateria.serial', 
        string='Escanear Seriales',
        domain="[('producto_id', '=', producto_id), ('estado', '=', 'disponible'), ('ubicacion_id', '=', parent.ubicacion_origen_id)]"
    )

    @api.onchange('serial_ids')
    def _onchange_serials(self):
        # Cuenta automáticamente cuántos seriales escaneaste
        if self.serial_ids:
            self.cantidad = len(self.serial_ids)