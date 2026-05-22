from odoo import models, fields, api

class BateriaReparacion(models.Model):
    _name = 'bateria.reparacion'
    _description = 'Orden de Reparación y Reposición'
    _rec_name = 'name'

    name = fields.Char(string='Referencia', required=True, copy=False, readonly=True, default='Nuevo')
    
    descripcion = fields.Char(string='Descripción de la reparación', required=True)
    tipo_reparacion = fields.Selection([
        ('reposicion', 'REPOSICION POR GARANTIA'),
        ('cambio', 'CAMBIO DE BATERÍA'),
        ('prestamo', 'PRESTAMO'),
        ('reparacion', 'REPARACIÓN'),
        ('revision', 'REVISIÓN'),
        ('regeneracion', 'REGENERACION')
    ], string='Tipo de Reparación', required=True)
    
    es_sistema_anterior = fields.Boolean(string='¿Batería del Sistema Anterior?', default=False, help="Activa esto si la batería se vendió en papel o en el sistema viejo antes de usar Odoo.")
    
    serial_id = fields.Many2one('bateria.serial', string='Serial en Odoo')
    serial_manual = fields.Char(string='Serial Físico (Manual)')
    
    fecha_compra_bateria = fields.Date(string='Fecha de Compra')
    tiempo_uso = fields.Char(string='Tiempo de Uso', compute='_compute_tiempo_uso', store=True)

    producto_id = fields.Many2one('bateria.producto', string='Producto a reparar', required=True)
    cantidad = fields.Float(string='Cantidad de producto', default=1.0)
    
    cliente_id = fields.Many2one('bateria.cliente', string='Cliente') 
    venta_id = fields.Many2one('bateria.orden.venta', string='Pedido de venta') 
    
    devolver = fields.Boolean(string='Devolver')
    
    fecha_programada = fields.Datetime(string='Fecha de Vencimiento', default=fields.Datetime.now)
    responsable_id = fields.Many2one('res.users', string='Responsable', default=lambda self: self.env.user)
    
    # 👇 CAMPOS DE PRÉSTAMO Y COBRANZA 👇
    producto_prestamo_id = fields.Many2one('bateria.producto', string='Modelo Prestado')
    serial_prestamo = fields.Char(string='Serial Batería de Préstamo', help="Escribe manualmente el serial de la batería prestada.")


    serial_entregado_id = fields.Many2one(
        'bateria.serial', 
        string='Nuevo Serial a Entregar (Inventario)', 
        domain="[('producto_id', '=', producto_id), ('estado', '=', 'disponible')]"
    )

    def action_convertir_reposicion(self):
        for rec in self:
            rec.tipo_reparacion = 'reposicion'
            return {
                'effect': {'fadeout': 'slow', 'message': 'Convertido a Reposición. Ahora escanea el nuevo serial a entregar.', 'type': 'rainbow_man'}
            }

    total_reparacion = fields.Float(string='Total a Cobrar', compute='_compute_total_reparacion', store=True)

    estado = fields.Selection([
        ('presupuesto', 'Presupuesto'),
        ('confirmado', 'Confirmado'),
        ('reparado', 'Reparado'),
        ('cancelado', 'Cancelado')
    ], string='Estado', default='presupuesto')
    
    pieza_ids = fields.One2many('bateria.reparacion.pieza', 'reparacion_id', string='Cobranza')
    notas_reparacion = fields.Text(string='Notas de reparación')
    notas_presupuesto = fields.Text(string='Notas del presupuesto')

    @api.depends('pieza_ids.subtotal')
    def _compute_total_reparacion(self):
        for r in self:
            r.total_reparacion = sum(p.subtotal for p in r.pieza_ids)

    @api.depends('fecha_compra_bateria')
    def _compute_tiempo_uso(self):
        from dateutil.relativedelta import relativedelta
        for r in self:
            if r.fecha_compra_bateria:
                hoy = fields.Date.context_today(self)
                diff = relativedelta(hoy, r.fecha_compra_bateria)
                meses = diff.years * 12 + diff.months
                dias = diff.days
                r.tiempo_uso = f"{meses} meses y {dias} días"
            else:
                r.tiempo_uso = "Sin registro de fecha"

    @api.onchange('serial_id')
    def _onchange_serial_id(self):
        if self.serial_id and not self.es_sistema_anterior:
            if self.serial_id.producto_id:
                self.producto_id = self.serial_id.producto_id.id
            if self.serial_id.orden_venta_id:
                self.venta_id = self.serial_id.orden_venta_id.id
                if self.serial_id.orden_venta_id.cliente_id:
                    self.cliente_id = self.serial_id.orden_venta_id.cliente_id.id
                if self.serial_id.orden_venta_id.fecha_creacion:
                    self.fecha_compra_bateria = self.serial_id.orden_venta_id.fecha_creacion.date()

    @api.onchange('es_sistema_anterior')
    def _onchange_es_sistema_anterior(self):
        if self.es_sistema_anterior:
            self.serial_id = False
            self.venta_id = False
            self.fecha_compra_bateria = False
        else:
            self.serial_manual = False
            self.fecha_compra_bateria = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('bateria.reparacion.seq') or 'REP-0001'
        return super(BateriaReparacion, self).create(vals_list)
    
    # 👇 NUEVOS CAMPOS PARA MANEJO DE CHATARRA / CANON 👇
    destino_bateria = fields.Selection([
        ('cliente', 'Se la lleva el cliente'),
        ('chatarra', '♻️ Dejada para Chatarra'),
        ('canon', '🎁 Dejada como Canon')
    ], string='Destino de Batería Dañada', default='cliente')
    
    bateria_procesada = fields.Boolean(string='Procesada en Sistema', default=False)

    def action_procesar_destino_bateria(self):
        for r in self:
            if r.bateria_procesada:
                raise UserError("Esta batería ya fue procesada y enviada a su destino.")
            
            if r.destino_bateria == 'cliente':
                raise UserError("El cliente seleccionó llevarse la batería. No hay nada que procesar.")
                
            desc_prod = r.producto_id.nombre if r.producto_id else 'Batería'
            serial_txt = r.serial_manual or (r.serial_id.nombre if r.serial_id else 'Sin Serial')
            cliente_txt = r.cliente_id.name if r.cliente_id else 'Cliente Desconocido'
            
            prefijo = "CHATARRA" if r.destino_bateria == 'chatarra' else "CANON"
            
            # Enviamos el registro a la tabla de chatarras
            self.env['bateria.chatarra'].create({
                'descripcion': f"[{prefijo}] Taller Ref: {r.name} | Cliente: {cliente_txt} | {desc_prod} (SN: {serial_txt})",
                'cantidad': 1,
                'fecha': fields.Date.context_today(self),
            })
                
            r.bateria_procesada = True
            
            return {
                'effect': {
                    'fadeout': 'slow',
                    'message': f'¡Excelente! La batería fue ingresada como {prefijo} al almacén de chatarras.',
                    'type': 'rainbow_man',
                }
            }

    def action_confirmar(self):
        for rec in self:
            rec.estado = 'confirmado'

    def action_reparar(self):
        for rec in self:
            # Si es reposición, validamos y descontamos del inventario
            if rec.tipo_reparacion == 'reposicion':
                if not rec.serial_entregado_id:
                    raise UserError("Para una Reposición por Garantía, debes seleccionar el 'Nuevo Serial a Entregar' que saldrá de tu inventario.")
                
                if rec.serial_entregado_id.estado != 'disponible':
                    raise UserError(f"El serial {rec.serial_entregado_id.nombre} ya no está disponible en inventario.")
                
                # Marcamos el serial nuevo como entregado/vendido
                rec.serial_entregado_id.write({'estado': 'vendido'})
                
                # Registramos la salida oficial en el sistema de inventario
                self.env['bateria.inventario'].create({
                    'fecha': fields.Datetime.now(),
                    'tipo_movimiento': 'salida',
                    'producto_id': rec.producto_id.id,
                    'cantidad': 1,
                    'ubicacion_id': rec.serial_entregado_id.ubicacion_id.id,
                    'nota': f"Salida por Garantía (Reposición) | Ref: {rec.name} | Cliente: {rec.cliente_id.name}"
                })
                
            rec.estado = 'reparado'

    def action_cancelar(self):
        for rec in self:
            rec.estado = 'cancelado'


class BateriaReparacionPieza(models.Model):
    _name = 'bateria.reparacion.pieza'
    _description = 'Líneas de Cobranza de Reparación'

    reparacion_id = fields.Many2one('bateria.reparacion', string='Reparación')
    tipo = fields.Selection([('servicio', 'Servicio Técnico'), ('repuesto', 'Repuesto / Insumo')], string='Tipo', default='servicio')
    producto_id = fields.Many2one('bateria.producto', string='Producto / Insumo')
    descripcion = fields.Char(string='Descripción del Cobro', required=True)
    cantidad = fields.Float(string='Cantidad', default=1.0)
    precio_unitario = fields.Float(string='Precio Unitario ($)')
    subtotal = fields.Float(string='Subtotal ($)', compute='_compute_subtotal')

    @api.depends('cantidad', 'precio_unitario')
    def _compute_subtotal(self):
        for rec in self:
            rec.subtotal = rec.cantidad * rec.precio_unitario