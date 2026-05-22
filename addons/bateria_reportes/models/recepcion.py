from odoo import models, fields, api
from odoo.exceptions import UserError

class BateriaRecepcion(models.Model):
    _name = 'bateria.recepcion'
    _description = 'Recepción de Almacén (Albarán de Entrada)'
    _rec_name = 'name'
    _order = 'fecha desc, id desc'

    name = fields.Char(string='Referencia de Albarán', required=True, copy=False, readonly=True, default='Nuevo')
    compra_id = fields.Many2one('bateria.compra', string='Pedido de Origen', readonly=True, ondelete='cascade')
    proveedor_id = fields.Many2one('bateria.proveedor', related='compra_id.proveedor_id', string='Proveedor')
    fecha = fields.Date(string='Fecha Programada', default=fields.Date.context_today)
    ubicacion_id = fields.Many2one('bateria.ubicacion', related='compra_id.ubicacion_id', string='Almacén Destino', store=True)
    
    estado = fields.Selection([
        ('listo', 'Preparado (Esperando Mercancía)'),
        ('hecho', 'Recibido y Validado'),
        ('cancelado', 'Cancelado')
    ], string='Estado', default='listo', tracking=True)

    linea_ids = fields.One2many('bateria.recepcion.linea', 'recepcion_id', string='Operaciones')

    def action_validar_recepcion(self):
        for rec in self:
            if rec.estado == 'hecho':
                continue
                
            for linea in rec.linea_ids:
                if not linea.seriales_escaneados:
                    raise UserError(f"Falta escanear los seriales para el modelo {linea.producto_id.nombre}.")
                
                # Convertimos el texto de seriales escaneados en una lista separada por comas o saltos de línea
                seriales_texto = linea.seriales_escaneados.replace('\n', ',').split(',')
                seriales_limpios = [s.strip() for s in seriales_texto if s.strip()]
                
                if len(seriales_limpios) != linea.cantidad_demandada:
                    raise UserError(f"Discrepancia en {linea.producto_id.nombre}: Se esperan {linea.cantidad_demandada} unidades, pero escaneaste {len(seriales_limpios)} seriales.")

                # 1. Crear los Seriales Físicos
                for serial in seriales_limpios:
                    self.env['bateria.serial'].create({
                        'nombre': serial,
                        'producto_id': linea.producto_id.id,
                        'ubicacion_id': rec.ubicacion_id.id,
                        'fecha_ingreso': fields.Date.context_today(self),
                        'estado': 'disponible'
                    })
                
                # 2. Registrar en el Historial de Inventario (Log)
                self.env['bateria.inventario'].create({
                    'fecha': fields.Datetime.now(),
                    'tipo_movimiento': 'entrada',
                    'producto_id': linea.producto_id.id,
                    'cantidad': linea.cantidad_demandada,
                    'ubicacion_id': rec.ubicacion_id.id,
                    'nota': f'📦 Entrada por Albarán {rec.name} | Seriales: {", ".join(seriales_limpios)}'
                })
                
                # 3. Actualizar la Orden de Compra
                linea_compra = rec.compra_id.linea_ids.filtered(lambda l: l.producto_maestro_id == linea.producto_id)
                if linea_compra:
                    linea_compra.cantidad_recibida = linea.cantidad_demandada
            
            rec.estado = 'hecho'
            rec.compra_id.estado = 'recibido' # Actualiza el pedido automáticamente a "Recibido"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('bateria.recepcion.seq') or f"IN/{fields.Date.context_today(self).strftime('%Y%m')}/XXX"
        return super().create(vals_list)

class BateriaRecepcionLinea(models.Model):
    _name = 'bateria.recepcion.linea'
    _description = 'Línea de Albarán'

    recepcion_id = fields.Many2one('bateria.recepcion', ondelete='cascade')
    producto_id = fields.Many2one('bateria.producto', string='Producto', required=True)
    cantidad_demandada = fields.Float(string='Demanda', required=True)
    
    # Campo para que el almacenista dispare la pistola de códigos de barras (uno por línea o separados por coma)
    seriales_escaneados = fields.Text(string='Escanear Seriales Aquí', help="Escanea o escribe los seriales separados por coma o salto de línea.")