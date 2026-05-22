from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import datetime, time

# =================================================================================
# NUEVO: BASE DE DATOS DE CHATARRAS
# =================================================================================
class BateriaChatarra(models.Model):
    _name = 'bateria.chatarra'
    _description = 'Registro de Chatarras Recibidas'
    _order = 'fecha desc, id desc'

    name = fields.Char(string='Referencia', default='Nuevo', readonly=True)
    fecha = fields.Date(string='Fecha de Recepción', default=fields.Date.context_today, required=True)
    orden_venta_id = fields.Many2one('bateria.orden.venta', string='Factura Origen', readonly=True, ondelete='set null')
    cliente_id = fields.Many2one('bateria.cliente', string='Cliente', related='orden_venta_id.cliente_id', store=True)
    descripcion = fields.Char(string='Descripción (Marca/Modelo y Estado)', required=True)
    cantidad = fields.Integer(string='Cantidad', required=True)
    
    estado = fields.Selection([
        ('almacen', 'En Almacén (Taller)'),
        ('enviada', 'Enviada a Planta / Vendida')
    ], string='Estado', default='almacen')

    def action_marcar_enviada(self):
        for r in self:
            r.estado = 'enviada'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('bateria.chatarra.seq') or 'CHT-0000'
        return super(BateriaChatarra, self).create(vals_list)

# =================================================================================
# EXTENSIÓN PARA GUARDAR EL COSTO REAL Y DEFINIR SI LLEVA SERIAL
# =================================================================================
class BateriaProductoExt(models.Model):
    _inherit = 'bateria.producto'
    costo_standard_usd = fields.Float(string='Costo Real (Con importación)', help="Costo real extraído de la estructura de costos (Excel)", default=0.0)
    
    requiere_serial = fields.Boolean(string='¿Requiere Serial? (Baterías)', default=True, help="Desmarca esto para vender cables, terminales de ojal, refrigerantes, etc.")

# =================================================================================
# 1. ORDEN DE VENTA
# =================================================================================
class OrdenVenta(models.Model):
    _name = 'bateria.orden.venta'
    _description = 'Orden de Venta'
    
    # 👇 NUEVO: SISTEMA MULTI-COMPAÑÍA NATIVO (Reemplaza a compania_origen) 👇
    company_id = fields.Many2one('res.company', string='Compañía', required=True, default=lambda self: self.env.company)

    tipo_documento = fields.Selection([
        ('nota_entrega', 'Nota de Entrega'),
        ('factura', 'Factura Fiscal')
    ], string='Tipo de Documento', required=True, default='nota_entrega')
    

    es_institucional = fields.Boolean(string='Es Cotización Institucional', default=False)

    referencia_pedido = fields.Char(string='No. Factura', required=True, copy=False, readonly=True, default='Nuevo')
    numero_control = fields.Char(string='Número de Control (SENIAT)', copy=False)
    fecha_creacion = fields.Datetime(string='Fecha', default=fields.Datetime.now)
    cliente_id = fields.Many2one('bateria.cliente', string='Cliente', required=True)
    rif = fields.Char(related='cliente_id.rif', string='Cédula / RIF', readonly=True)
    telefono = fields.Char(related='cliente_id.telefono', string='Teléfono', readonly=True)
    direccion = fields.Text(related='cliente_id.direccion', string='Dirección', readonly=True)
    
    ubicacion_id = fields.Many2one('bateria.ubicacion', string='Almacén de Despacho', required=True)
    despachado = fields.Boolean(string='Mercancía Entregada', default=False, copy=False)
    fecha_despacho_real = fields.Date(string='Fecha de Despacho Real', readonly=True)
    
    tipo_venta = fields.Selection([('caja', 'Caja'), ('administrado', 'Administrado')], default='caja')

    estado = fields.Selection([
        ('borrador', 'Presupuesto'), 
        ('parcial', 'Abono'),
        ('pagado', 'Pagado')], 
        string='Estado', default='borrador', copy=False)

    traslado_necesario = fields.Boolean(compute='_compute_traslado_necesario')
    asiento_id = fields.Many2one('bateria.asiento', string='Asiento Contable', readonly=True)
    traslado_id = fields.Many2one('bateria.traslado', string='Traslado Solicitado', readonly=True)
    traslado_estado = fields.Selection(related='traslado_id.estado', string='Estado del Traslado')

    es_venta_historica = fields.Boolean(string='Cargar Venta al Pasado', default=False, help="Activa esto para registrar una factura vieja.")
    fecha_historica = fields.Date(string='Fecha Real de la Venta Vieja')

    @api.depends('linea_ids.cantidad', 'linea_ids.producto_id', 'es_venta_historica')
    def _compute_traslado_necesario(self):
        for r in self:
            necesario = False
            for linea in r.linea_ids:
                if linea.producto_id and linea.producto_id.requiere_serial:
                    qty_racksito = self.env['bateria.serial'].search_count([
                        ('producto_id', '=', linea.producto_id.id),
                        ('estado', '=', 'disponible'),
                        ('ubicacion_id.nombre_completo', 'ilike', 'racksito')
                    ])
                    if linea.cantidad > qty_racksito and not r.es_venta_historica:
                        necesario = True
            r.traslado_necesario = necesario

    def action_solicitar_traslado(self):
        for r in self:
            racksito = self.env['bateria.ubicacion'].search([('nombre_completo', 'ilike', 'racksito')], limit=1)
            galpon = self.env['bateria.ubicacion'].search([('nombre_completo', 'not ilike', 'racksito')], limit=1)
            
            lineas_traslado = []
            
            for linea in r.linea_ids:
                if not linea.producto_id or not linea.producto_id.requiere_serial:
                    continue 
                    
                qty_racksito = self.env['bateria.serial'].search_count([
                    ('producto_id', '=', linea.producto_id.id),
                    ('estado', '=', 'disponible'),
                    ('ubicacion_id.nombre_completo', 'ilike', 'racksito')
                ])
                faltante = linea.cantidad - qty_racksito
                
                if faltante > 0:
                    lineas_traslado.append((0, 0, {
                        'producto_id': linea.producto_id.id,
                        'cantidad': faltante,
                    }))
                    
            if lineas_traslado:
                nuevo_traslado = self.env['bateria.traslado'].create({
                    'name': f'Solicitud Factura {r.referencia_pedido}',
                    'ubicacion_origen_id': galpon.id,
                    'ubicacion_destino_id': racksito.id,
                    'linea_ids': lineas_traslado,
                    'nota': f'Traslado solicitado desde la zona de ventas.',
                    'estado': 'borrador'
                })
                r.traslado_id = nuevo_traslado.id

    def action_confirmar_venta_y_descargar(self):
        inventory_model = self.env['bateria.inventario']
        for orden in self:
            
            fecha_accion = fields.Datetime.now()
            fecha_despacho = fields.Date.context_today(self)
            
            if orden.es_venta_historica:
                if not orden.fecha_historica:
                    raise UserError("Debes indicar la 'Fecha Real de la Venta Vieja'.")
                fecha_accion = datetime.combine(orden.fecha_historica, time(12, 0, 0))
                fecha_despacho = orden.fecha_historica
                orden.fecha_creacion = fecha_accion
            
            if orden.traslado_necesario and not orden.es_venta_historica:
                if not orden.traslado_id:
                    raise UserError("🛑 ¡ALTO! Faltan baterías en el Racksito. Haz clic en 'Solicitar Traslado a Galpón' primero.")
                elif orden.traslado_id.estado != 'realizado':
                    raise UserError(f"⏳ El traslado ({orden.traslado_id.name}) aún no está completado.")
            
            if not orden.pago_ids and orden.condiciones_pago not in ('credito', 'canon'):
                raise UserError("🛑 ¡ALTO! Debes registrar al menos un pago en la pestaña 'Registro de Pagos' antes de despachar.")

            if not orden.linea_ids or orden.despachado:
                continue
                
            for linea in orden.linea_ids:
                if linea.producto_id and linea.producto_id.requiere_serial:
                    
                    if orden.es_venta_historica and linea.seriales_masivos:
                        seriales_limpios = [s.strip() for s in linea.seriales_masivos.replace('\n', ',').split(',') if s.strip()]
                        nuevos_seriales_ids = []
                        
                        for sn in seriales_limpios:
                            existente = self.env['bateria.serial'].search([('nombre', '=', sn)], limit=1)
                            if not existente:
                                existente = self.env['bateria.serial'].create({
                                    'nombre': sn,
                                    'producto_id': linea.producto_id.id,
                                    'ubicacion_id': orden.ubicacion_id.id,
                                    'estado': 'disponible',
                                    'fecha_ingreso': orden.fecha_historica
                                })
                            else:
                                existente.write({
                                    'ubicacion_id': orden.ubicacion_id.id,
                                    'estado': 'disponible'
                                })
                            nuevos_seriales_ids.append(existente.id)
                        
                        linea.serial_ids = [(6, 0, nuevos_seriales_ids)]
                        linea.cantidad = len(nuevos_seriales_ids)
                    
                    if not linea.serial_ids or len(linea.serial_ids) != linea.cantidad:
                        raise UserError(f"🛑 ¡SEGURIDAD DE INVENTARIO! En el modelo '{linea.producto_id.nombre}' estás pidiendo {linea.cantidad} unidad(es), pero no has escaneado/pegado los seriales físicos.")
                    
                    if not linea.saltar_regla_antiguedad and not orden.es_venta_historica:
                        viejas = self.env['bateria.serial'].search([
                            ('producto_id', '=', linea.producto_id.id),
                            ('estado', '=', 'disponible'),
                            ('ubicacion_id.nombre_completo', 'ilike', 'racksito')
                        ], order='create_date ASC', limit=linea.cantidad)
                        
                        viejas_ids = viejas.mapped('id')
                        seleccionadas_ids = linea.serial_ids.mapped('id')
                        
                        if set(viejas_ids) != set(seleccionadas_ids):
                            nombres_viejos = " | ".join(viejas.mapped('nombre'))
                            raise UserError(f"🛑 REGLA DE ANTIGÜEDAD (PEPS) ACTIVADA 🛑\n\nEstás intentando vender una batería más nueva del modelo '{linea.producto_id.nombre}'. Por política de la empresa, debes vender las más viejas primero.\n\n👉 DEBES SELECCIONAR ESTOS SERIALES OBLIGATORIAMENTE:\n{nombres_viejos}")

                    for serial in linea.serial_ids:
                        vals_serial = {'estado': 'vendido', 'orden_venta_id': orden.id}
                        if orden.es_venta_historica:
                            vals_serial['fecha_ingreso'] = orden.fecha_historica
                        serial.write(vals_serial)

                        if orden.aplica_promocion and orden.meses_garantia_promo > 0:
                            from dateutil.relativedelta import relativedelta
                            vals_serial['fecha_vencimiento'] = fecha_despacho + relativedelta(months=orden.meses_garantia_promo)
                            
                        serial.write(vals_serial)

                        # 👇 NUEVO: CÁLCULO DINÁMICO DE GARANTÍA 👇
                        meses_aplicar = 0
                        if orden.aplica_promocion and orden.meses_garantia_promo > 0:
                            meses_aplicar = orden.meses_garantia_promo
                        elif orden.tipo_bateria_garantia == 'moto':
                            meses_aplicar = 1
                        elif orden.tipo_bateria_garantia == 'ups':
                            meses_aplicar = 6

                        if meses_aplicar > 0:
                            from dateutil.relativedelta import relativedelta
                            vals_serial['fecha_vencimiento'] = fecha_despacho + relativedelta(months=meses_aplicar)
                            
                        serial.write(vals_serial)

                if linea.producto_id:
                    inventory_model.create({
                        'fecha': fecha_accion,
                        'tipo_movimiento': 'salida',
                        'producto_id': linea.producto_id.id,
                        'cantidad': linea.cantidad,
                        'orden_venta_id': orden.id,
                        'ubicacion_id': orden.ubicacion_id.id,
                        'nota': f"Venta Histórica Ref: {orden.referencia_pedido}" if orden.es_venta_historica else (f"Venta Ref: {orden.referencia_pedido} (Canon)" if orden.condiciones_pago == 'canon' else f"Venta Ref: {orden.referencia_pedido}")
                    })
            
            orden.fecha_despacho_real = fecha_despacho
            orden.despachado = True
            if orden.estado == 'borrador':
                orden.estado = 'parcial' if orden.saldo_pendiente > 0.01 else 'pagado'

            if orden.cantidad_chatarras and orden.cantidad_chatarras != '0' and orden.ingresar_chatarra:
                ya_existe = self.env['bateria.chatarra'].search([('orden_venta_id', '=', orden.id)])
                if not ya_existe:
                    qty = int(orden.cantidad_chatarras[0])
                    
                    desc_final = orden.descripcion_chatarra or 'Ingresada por Venta'
                    if qty >= 2 and orden.descripcion_chatarra_2:
                        desc_final += f" | {orden.descripcion_chatarra_2}"
                    if qty == 3 and orden.descripcion_chatarra_3:
                        desc_final += f" | {orden.descripcion_chatarra_3}"

                    self.env['bateria.chatarra'].create({
                        'orden_venta_id': orden.id,
                        'cliente_id': orden.cliente_id.id,
                        'cantidad': qty,
                        'descripcion': desc_final,
                        'fecha': orden.fecha_despacho_real,
                    })

            # 👇 FRENO CONTABLE INYECTADO AQUÍ 👇
            if not orden.asiento_id and orden.tipo_documento == 'factura':
                diario = self.env['bateria.diario'].search([('tipo', '=', 'venta'), ('company_id', '=', orden.company_id.id)], limit=1)
                if diario:
                    c_cxc = self.env['bateria.cuenta.contable'].search([('name', 'ilike', 'por Cobrar'), '|', ('company_id', '=', False), ('company_id', '=', orden.company_id.id)], limit=1)
                    c_ingreso = self.env['bateria.cuenta.contable'].search([('name', 'ilike', 'Venta'), '|', ('company_id', '=', False), ('company_id', '=', orden.company_id.id)], limit=1) or c_cxc
                    c_iva = self.env['bateria.cuenta.contable'].search([('name', 'ilike', 'IVA'), '|', ('company_id', '=', False), ('company_id', '=', orden.company_id.id)], limit=1) or c_cxc
                    
                    monto_total = orden.total_global_usd if orden.moneda == 'usd' else orden.total_global_bs
                    monto_base = orden.subtotal_bruto_usd if orden.moneda == 'usd' else orden.subtotal_bruto_bs
                    monto_iva = orden.total_iva_usd if orden.moneda == 'usd' else orden.total_iva_bs
                    
                    asiento = self.env['bateria.asiento'].create({
                        'fecha': orden.fecha_creacion, 
                        'referencia': f"Venta: {orden.referencia_pedido}",
                        'diario_id': diario.id, 
                        'estado': 'asentado',
                        'company_id': orden.company_id.id
                    })
                    self.env['bateria.apunte'].create({'asiento_id': asiento.id, 'cuenta_id': c_cxc.id, 'cliente_id': orden.cliente_id.id, 'nombre': "Cuentas por Cobrar", 'debe': monto_total, 'haber': 0.0})
                    if monto_base > 0:
                        self.env['bateria.apunte'].create({'asiento_id': asiento.id, 'cuenta_id': c_ingreso.id, 'nombre': "Ingresos por Ventas", 'debe': 0.0, 'haber': monto_base})
                    if monto_iva > 0:
                        self.env['bateria.apunte'].create({'asiento_id': asiento.id, 'cuenta_id': c_iva.id, 'nombre': "IVA Débito Fiscal", 'debe': 0.0, 'haber': monto_iva})
                        
                    orden.asiento_id = asiento.id
            
        return {'effect': {'fadeout': 'slow', 'message': '¡Venta Procesada Exitosamente!', 'type': 'rainbow_man'}}
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('referencia_pedido', 'Nuevo') == 'Nuevo':
                vals['referencia_pedido'] = self.env['ir.sequence'].next_by_code('bateria.orden.venta.secuencia') or 'Nuevo'
        return super(OrdenVenta, self).create(vals_list)

    def _get_tasa_bcv_actual(self):
        tasa = self.env['ir.config_parameter'].sudo().get_param('bateria.tasa_usdt', default='1.0')
        return float(tasa)

    moneda = fields.Selection([('usd', 'USD'), ('bs', 'Bs')], required=True, default='usd')
    tasa_bcv = fields.Float(string='Tasa BCV', default=_get_tasa_bcv_actual)
    tasa_cambio = fields.Float(string='Tasa Cambio')
    usar_tasa_personalizada = fields.Boolean()
    
    total = fields.Float(string='Total', compute='_compute_total', store=True)
    total_iva = fields.Float(string='Total IVA', compute='_compute_total', store=True)
    subtotal_bruto_usd = fields.Float(string='Subtotal ($)', compute='_compute_total', store=True)
    subtotal_bruto_bs = fields.Float(string='Subtotal (Bs)', compute='_compute_total', store=True)
    total_iva_usd = fields.Float(string='IVA ($)', compute='_compute_total', store=True)
    total_iva_bs = fields.Float(string='IVA (Bs)', compute='_compute_total', store=True)
    monto_descuento_usd = fields.Float(string='Descuento ($)', compute='_compute_total', store=True)
    monto_descuento_bs = fields.Float(string='Descuento (Bs)', compute='_compute_total', store=True)
    subtotal_bruto = fields.Float(compute='_compute_total', store=True)
    monto_descuento = fields.Float(compute='_compute_total', store=True)
    descuento_visual = fields.Char(compute='_compute_total', store=True)
    
    total_global_bs = fields.Float(string='Total Bs', compute='_compute_totales_globales', store=True)
    total_global_usd = fields.Float(string='Total $', compute='_compute_totales_globales', store=True)
    texto_conversion = fields.Char(string='Conv', compute='_compute_totales_globales', store=True)

    @api.depends('total', 'moneda', 'tasa_aplicada')
    def _compute_totales_globales(self):
        for r in self:
            tasa = r.tasa_aplicada if r.tasa_aplicada > 0 else 1.0
            if r.moneda == 'usd':
                r.total_global_usd = r.total
                r.total_global_bs = r.total * tasa
                r.texto_conversion = f"{r.total_global_bs:,.2f} Bs"
            else:
                r.total_global_bs = r.total
                r.total_global_usd = r.total / tasa
                r.texto_conversion = f"{r.total_global_usd:,.2f} $"
    
    pago_inicial = fields.Float(string='Pago Inicial', compute='_compute_estado_cuenta', store=True)
    pago_inicial_texto = fields.Char(string='Pago Inicial (Abonos)', compute='_compute_pago_inicial_texto')
    
    pago_divisa = fields.Char(string='Divisa', compute='_compute_detalles_pago', store=True)
    pago_referencia = fields.Char(string='Referencia / Banco / Serial', compute='_compute_detalles_pago', store=True)
    fechas_abonos = fields.Char(string='Historial de Abonos', compute='_compute_fechas_abonos')
    
    actividades = fields.Char()
    
    billetes_vuelto_ids = fields.One2many('bateria.vuelto.billete', 'orden_id', string='Desglose de Vuelto')
    vuelto_entregado_usd = fields.Float(string='Vuelto Entregado ($)', compute='_compute_vuelto_entregado', store=True)

    vuelto_pago_movil_bs = fields.Float(string='Vuelto en Pago Móvil (Bs)', default=0.0)
    referencia_vuelto_pm = fields.Char(string='Referencia Pago Móvil')
    

    @api.depends('billetes_vuelto_ids.subtotal')
    def _compute_vuelto_entregado(self):
        for r in self:
            r.vuelto_entregado_usd = sum(b.subtotal for b in r.billetes_vuelto_ids)
            
    total_ganancia_usd = fields.Float(string='Ganancia Neta ($)', compute='_compute_ganancia_total', store=True)

    @api.depends('linea_ids.ganancia_usd', 'monto_descuento_usd', 'condiciones_pago', 'linea_ids.costo_unitario_usd', 'linea_ids.cantidad')
    def _compute_ganancia_total(self):
        for r in self:
            if r.condiciones_pago == 'canon':
                costo_total = sum(l.costo_unitario_usd * l.cantidad for l in r.linea_ids)
                r.total_ganancia_usd = -costo_total
            else:
                ganancia_bruta = sum(l.ganancia_usd for l in r.linea_ids)
                r.total_ganancia_usd = ganancia_bruta - r.monto_descuento_usd
    
    condiciones_pago = fields.Selection([
        ('contado', 'De Contado'),
        ('credito', 'Crédito (Por Cobrar)'),
        ('consignacion', 'Consignación (Apartado)'),
        ('cashea_60', 'Cashea 60% Nivel 1'),
        ('cashea_50', 'Cashea 50% Nivel 2'),
        ('cashea_40', 'Cashea 40% Nivel 3, 4 y 5'),
        ('canon', 'Canon (Regalo / Sin Cobro)')
    ], string='Condiciones de Pago')
    
    nota_canon = fields.Text(string='Motivo del Canon')
    
    tarifa_id = fields.Many2one('bateria.tarifa', string='Tarifa de Cliente')

    aplica_iva = fields.Boolean(string='Aplica IVA (16%)', default=False)
    
    def action_agregar_iva(self):
        for r in self: r.aplica_iva = True

    def action_quitar_iva(self):
        for r in self: r.aplica_iva = False
    
    monto_inicial_requerido = fields.Float(string='Inicial a Pagar (Cashea)', compute='_compute_cashea', store=True)
    
    cantidad_chatarras = fields.Selection([('0','0'), ('1','1'), ('2','2'), ('3','3 (50%)')], default='0', string="Cant. Chatarras")
    descripcion_chatarra = fields.Char(string='Descripción de Chatarra', help="Especifique marca, modelo y estado de la chatarra recibida.")
    descripcion_chatarra_2 = fields.Char(string='Descripción Chatarra 2')
    descripcion_chatarra_3 = fields.Char(string='Descripción Chatarra 3')


    aplica_promocion = fields.Boolean(string='🎁 Activar Promoción', default=False)
    precio_promocional_usd = fields.Float(string='Precio Final Promoción ($)', help="El precio exacto en el que quedará la batería.")
    meses_garantia_promo = fields.Integer(string='Meses de Garantía', default=6, help="Los meses de garantía que tendrá esta batería.")
    ingresar_chatarra = fields.Boolean(
        string='♻️ ¿Ingresar al Inventario de Chatarras?', 
        compute='_compute_ingresar_chatarra', 
        store=True, 
        readonly=False,
        help="Si la factura es Canon, esto se desmarca automáticamente para no sumar la chatarra."
    )

    promo_instagram = fields.Boolean(string='¿Comentario en Instagram? (-$5)')


    tipo_bateria_garantia = fields.Selection([
        ('carro', '🚗 Carro (Estándar)'),
        ('moto', '🏍️ Moto (1 Mes)'),
        ('ups', '🔋 UPS / Inversor (6 Meses)')
    ], string='Aplicación de la Batería', default='carro', required=True)

    meses_garantia_impresos = fields.Char(string='Garantía a Imprimir', compute='_compute_meses_garantia_impresos')

    @api.depends('tipo_bateria_garantia', 'aplica_promocion', 'meses_garantia_promo')
    def _compute_meses_garantia_impresos(self):
        for r in self:
            if r.aplica_promocion and r.meses_garantia_promo > 0:
                r.meses_garantia_impresos = f"{r.meses_garantia_promo} Meses (Promocional)"
            elif r.tipo_bateria_garantia == 'moto':
                r.meses_garantia_impresos = "1 Mes"
            elif r.tipo_bateria_garantia == 'ups':
                r.meses_garantia_impresos = "6 Meses"
            else:
                r.meses_garantia_impresos = "Condiciones Estándar"


    @api.onchange('promo_instagram', 'cantidad_chatarras')
    def _onchange_promo_instagram(self):
        cantidad_chatarra_num = int(self.cantidad_chatarras or '0')
        if self.promo_instagram and cantidad_chatarra_num >= 3:
            self.promo_instagram = False
            return {
                'warning': {
                    'title': '🛑 Promoción No Aplicable',
                    'message': 'El descuento de $5 por Instagram NO aplica si el cliente está entregando 3 o más chatarras.'
                }
            }

    @api.depends('condiciones_pago')
    def _compute_ingresar_chatarra(self):
        for r in self:
            if r.condiciones_pago == 'canon':
                r.ingresar_chatarra = False
            else:
                r.ingresar_chatarra = True
    
    agendar_recambio = fields.Boolean(
        string='🔔 Agendar Próximo Cambio', 
        default=False, 
        help="Activa esto para agendar cuándo el cliente necesitará una batería nueva."
    )
    fecha_vencimiento = fields.Date(
        string='Fecha Estimada de Cambio', 
        help="Fecha en la que se estima que la batería perderá su vida útil."
    )

    lista_precios = fields.Char(compute='_compute_lista_precios')
    lista_productos = fields.Char(compute='_compute_lista_productos')

    
    producto_principal_id = fields.Many2one('bateria.producto', string='Modelo Vendido', compute='_compute_producto_principal', store=True)

    @api.depends('linea_ids.producto_id')
    def _compute_producto_principal(self):
        for r in self:
            # Toma el primer producto de la factura para graficarlo
            productos = r.linea_ids.mapped('producto_id')
            r.producto_principal_id = productos[0].id if productos else False

    # 👇 2. BOTÓN MÁGICO ACTUALIZADO 👇
    def action_recalcular_graficos(self):
        todas_las_ventas = self.env['bateria.orden.venta'].search([])
        for r in todas_las_ventas:
            productos = r.linea_ids.mapped('producto_id')
            r.producto_principal_id = productos[0].id if productos else False
            
        return {
            'effect': {'fadeout': 'slow', 'message': '¡Modelos Sincronizados Oficialmente! Ve al gráfico.', 'type': 'rainbow_man'}
        }
    
    lista_seriales = fields.Char(string='Seriales Entregados', compute='_compute_lista_seriales')

    linea_ids = fields.One2many('bateria.orden.linea', 'orden_id', string='Líneas')
    pago_ids = fields.One2many('bateria.pago', 'orden_venta_id', string='Pagos')
    
    saldo_pendiente = fields.Float(compute='_compute_estado_cuenta', store=True)

    moneda_referencia = fields.Selection([
        ('usdt', 'USDT (Binance/Paralelo)'), 
        ('usd', 'Dólar BCV'), 
        ('eur', 'Euro BCV')
    ], string='Tasa Referencia', default='usdt', required=True)
    
    tasa_aplicada = fields.Float(string='Tasa del Día', compute='_compute_tasa_aplicada', store=True)
    
    total_final_bs = fields.Float(string='Total Neto (Bs)', compute='_compute_totales_nuevos', store=True)
    total_final_ref = fields.Float(string='Total Neto (Divisa)', compute='_compute_totales_nuevos', store=True)
    simbolo_moneda = fields.Char(compute='_compute_totales_nuevos', store=True)

    @api.depends('linea_ids.serial_ids')
    def _compute_lista_seriales(self):
        for r in self:
            seriales = []
            for linea in r.linea_ids:
                for serial in linea.serial_ids:
                    seriales.append(serial.display_name or 'S/N')
            r.lista_seriales = " | ".join(seriales) if seriales else "Ninguno"

    @api.depends('moneda_referencia', 'usar_tasa_personalizada', 'tasa_cambio')
    def _compute_tasa_aplicada(self):
        for r in self:
            if r.usar_tasa_personalizada and r.tasa_cambio > 0:
                r.tasa_aplicada = r.tasa_cambio
            else:
                if r.moneda_referencia == 'usdt': param = 'bateria.tasa_usdt'
                elif r.moneda_referencia == 'usd': param = 'bateria.tasa_bcv_usd'
                else: param = 'bateria.tasa_bcv_eur'
                r.tasa_aplicada = float(self.env['ir.config_parameter'].sudo().get_param(param, default='1.0'))

    def action_actualizar_tasa_bcv_manual(self):
        try:
            self.env['bateria.bcv.scraper'].actualizar_tasas_completas()
        except: 
            pass
        for r in self:
            r._compute_tasa_aplicada()

    @api.onchange('moneda_referencia', 'usar_tasa_personalizada', 'tasa_cambio')
    def _onchange_forzar_actualizacion_totales(self):
        if self.usar_tasa_personalizada and self.tasa_cambio > 0:
            nueva_tasa = self.tasa_cambio
        else:
            if self.moneda_referencia == 'usdt': param = 'bateria.tasa_usdt'
            elif self.moneda_referencia == 'usd': param = 'bateria.tasa_bcv_usd'
            else: param = 'bateria.tasa_bcv_eur'
            nueva_tasa = float(self.env['ir.config_parameter'].sudo().get_param(param, default='1.0'))
            
        self.tasa_bcv = nueva_tasa 
        for linea in self.linea_ids:
            if linea.precio_usd:
                tasa_linea_calc = linea.tasa_linea if (linea.usar_tasa_linea and linea.tasa_linea > 0) else nueva_tasa
                linea.precio_bs = linea.precio_usd * tasa_linea_calc

    def action_actualizar_tasa_bcv_manual(self):
        self.env['bateria.bcv.scraper'].actualizar_tasas_completas()
        for r in self:
            if r.moneda_referencia == 'usdt': param = 'bateria.tasa_usdt'
            elif r.moneda_referencia == 'usd': param = 'bateria.tasa_bcv_usd'
            else: param = 'bateria.tasa_bcv_eur'
            r.tasa_bcv = float(self.env['ir.config_parameter'].sudo().get_param(param, default='1.0'))
        self._compute_tasa_aplicada()

    @api.onchange('moneda_referencia', 'tasa_aplicada', 'tarifa_id')
    def _onchange_recalcular_lineas_por_tasa(self):
        for linea in self.linea_ids:
            if linea.producto_id:
                precio_base_divisa = linea.producto_id.precio_base_usd
                if self.tarifa_id:
                    regla = self.env['bateria.producto.tarifa'].search([
                        ('producto_id', '=', linea.producto_id.id),
                        ('tarifa_id', '=', self.tarifa_id.id)
                    ], limit=1)
                    if regla:
                        if regla.moneda == 'usd': 
                            precio_base_divisa = regla.precio
                        else: 
                            tasa_g = float(self.env['ir.config_parameter'].sudo().get_param('bateria.tasa_usdt', default='1.0'))
                            precio_base_divisa = regla.precio / tasa_g if tasa_g > 0 else regla.precio
                
                tasa = linea.tasa_linea if (linea.usar_tasa_linea and linea.tasa_linea > 0) else (self.tasa_aplicada if self.tasa_aplicada > 0 else 1.0)
                linea.precio_bs = precio_base_divisa * tasa

    @api.depends('total', 'tasa_aplicada', 'moneda_referencia')
    def _compute_totales_nuevos(self):
        for r in self:
            tasa = r.tasa_aplicada if r.tasa_aplicada > 0 else 1.0
            if r.moneda == 'bs':
                r.total_final_bs = r.total
                r.total_final_ref = r.total / tasa
            else:
                r.total_final_bs = r.total * tasa
                r.total_final_ref = r.total
                
            if r.moneda_referencia == 'eur': r.simbolo_moneda = '€'
            elif r.moneda_referencia == 'usdt': r.simbolo_moneda = 'USDT'
            else: r.simbolo_moneda = '$'

    @api.depends('total', 'condiciones_pago')
    def _compute_cashea(self):
        for r in self:
            if r.condiciones_pago == 'cashea_60': r.monto_inicial_requerido = r.total * 0.60
            elif r.condiciones_pago == 'cashea_50': r.monto_inicial_requerido = r.total * 0.50
            elif r.condiciones_pago == 'cashea_40': r.monto_inicial_requerido = r.total * 0.40
            else: r.monto_inicial_requerido = 0.0

    def action_ir_a_pagar(self):
        for r in self:
            if r.estado == 'borrador': 
                r.estado = 'parcial' if r.saldo_pendiente > 0.01 else 'pagado'

    def action_dummy(self):
        return True

    @api.depends('linea_ids', 'linea_ids.producto_id')
    def _compute_lista_productos(self):
        for r in self: r.lista_productos = " | ".join([l.producto_id.nombre for l in r.linea_ids if l.producto_id])


    def action_recalcular_graficos(self):
        todas_las_ventas = self.env['bateria.orden.venta'].search([])
        for r in todas_las_ventas:
            r.lista_productos = " | ".join([l.producto_id.nombre for l in r.linea_ids if l.producto_id])
        return {
            'effect': {'fadeout': 'slow', 'message': '¡Historial Sincronizado! Ve a ver tus gráficos.', 'type': 'rainbow_man'}
        }
    @api.depends('linea_ids')
    def _compute_lista_precios(self):
        for r in self: r.lista_precios = "Ver detalle"

    @api.depends('pago_ids.fecha_pago', 'pago_ids.monto')
    def _compute_pago_inicial_texto(self):
        for r in self:
            if not r.pago_ids:
                r.pago_inicial_texto = "0.00"
                continue
            pagos = r.pago_ids.sorted(key=lambda p: p.fecha_pago)
            primer_pago = pagos[0].monto
            texto = f"{primer_pago:,.2f}"
            if len(pagos) > 1:
                abonos = [f"{p.monto:,.2f}" for p in pagos[1:]]
                texto += f" (Abonos: {', '.join(abonos)})"
            r.pago_inicial_texto = texto

    @api.depends('pago_ids', 'pago_ids.moneda', 'pago_ids.tipo_pago', 'pago_ids.banco', 'pago_ids.referencia_banco', 'pago_ids.serial_billetes', 'condiciones_pago')
    def _compute_detalles_pago(self):
        mapeo_bancos = {'banesco': 'Banesco', 'venezuela': 'Venezuela', 'mercantil': 'Mercantil', 'bnc': 'BNC', 'provincial': 'Provincial', 'bofa': 'Bank of America'}
        mapeo_tipos = {'efectivo': 'Efectivo', 'pago_movil': 'Pago Móvil', 'transferencia': 'Transf.', 'zelle': 'Zelle', 'punto': 'Punto', 'biopago': 'Biopago', 'cashea': 'Cashea', 'saldo_favor': 'Saldo a Favor'}
        for r in self:
            if r.condiciones_pago == 'canon':
                r.pago_divisa = "CANON"
                r.pago_referencia = r.nota_canon or "Sin Cobro"
                continue
                
            divisas = list(set([p.moneda.upper() for p in r.pago_ids if p.moneda]))
            r.pago_divisa = ", ".join(divisas) if divisas else "Sin Pago"
            refs = []
            for p in r.pago_ids:
                tipo = mapeo_tipos.get(p.tipo_pago, p.tipo_pago)
                if p.tipo_pago == 'efectivo':
                    serial = p.serial_billetes or 'Sin Serial'
                    refs.append(f"{tipo} (Serial: {serial})")
                elif p.tipo_pago == 'saldo_favor':
                    ref_vieja = p.referencia_banco or 'Reintegro'
                    refs.append(f"{tipo} (Origen: {ref_vieja})")
                else:
                    banco = mapeo_bancos.get(p.banco, p.banco) if p.banco else ''
                    txt_banco = f" {banco}" if banco else ""
                    txt_ref = f" (Ref: {p.referencia_banco})" if p.referencia_banco else ""
                    refs.append(f"{tipo}{txt_banco}{txt_ref}")
            r.pago_referencia = " | ".join(refs) if refs else "Sin Pago"

    @api.depends('pago_ids.fecha_pago', 'pago_ids.monto', 'pago_ids.moneda')
    def _compute_fechas_abonos(self):
        for r in self:
            abonos = []
            for p in r.pago_ids:
                if p.fecha_pago:
                    fecha_str = p.fecha_pago.strftime('%d/%m/%Y')
                    mon = p.moneda.upper() if p.moneda else ''
                    abonos.append(f"{fecha_str}: {p.monto} {mon}")
            r.fechas_abonos = " | ".join(abonos) if abonos else "Sin abonos"

    @api.depends('linea_ids.subtotal', 'aplica_iva', 'cantidad_chatarras', 'moneda', 'tasa_aplicada', 'promo_instagram')
    def _compute_total(self):
        tasa_bcv_oficial = float(self.env['ir.config_parameter'].sudo().get_param('bateria.tasa_bcv_usd', default='1.0'))
        
        for r in self:
            subtotal = sum(l.subtotal for l in r.linea_ids)
            total_iva = subtotal * 0.16 if r.aplica_iva else 0.0
            r.subtotal_bruto = subtotal
            r.total_iva = total_iva
            
            tasa_factura = r.tasa_aplicada if r.tasa_aplicada > 0 else 1.0
            
            desc_real = 0.0
            desc_usd = 0.0
            desc_bs = 0.0
            
            if r.cantidad_chatarras == '1':
                desc_usd = 5.0
                desc_bs = 5.0 * tasa_bcv_oficial
                desc_real = desc_usd if r.moneda == 'usd' else desc_bs
            elif r.cantidad_chatarras == '2':
                desc_usd = 10.0
                desc_bs = 10.0 * tasa_bcv_oficial
                desc_real = desc_usd if r.moneda == 'usd' else desc_bs
            elif r.cantidad_chatarras == '3':
                desc_real = subtotal * 0.50
                if r.moneda == 'usd':
                    desc_usd = desc_real
                    desc_bs = desc_real * tasa_factura
                else:
                    desc_bs = desc_real
                    desc_usd = desc_real / tasa_factura if tasa_factura > 0 else 0.0

            if r.promo_instagram:
                desc_usd += 5.0
                desc_bs += (5.0 * tasa_bcv_oficial)
                desc_real += 5.0 if r.moneda == 'usd' else (5.0 * tasa_bcv_oficial)

            r.monto_descuento = desc_real
            r.total = max((subtotal + total_iva) - desc_real, 0.0)
            
            if r.aplica_promocion and r.precio_promocional_usd > 0:
                total_sin_descuento = subtotal + total_iva
                diferencia_usd = total_sin_descuento - r.precio_promocional_usd
                
                if diferencia_usd > 0:
                    desc_usd = diferencia_usd
                    desc_bs = diferencia_usd * tasa_factura
                    desc_real = desc_usd if r.moneda == 'usd' else desc_bs

            # 4. AHORA SÍ: ASIGNACIÓN DE TOTALES
            r.monto_descuento = desc_real
            r.total = max((subtotal + total_iva) - desc_real, 0.0)

            if r.moneda == 'usd':
                r.subtotal_bruto_usd = r.subtotal_bruto
                r.subtotal_bruto_bs = r.subtotal_bruto * tasa_factura
                r.total_iva_usd = r.total_iva
                r.total_iva_bs = r.total_iva * tasa_factura
                r.monto_descuento_usd = desc_usd
                r.monto_descuento_bs = desc_bs
            else:
                r.subtotal_bruto_bs = r.subtotal_bruto
                r.subtotal_bruto_usd = r.subtotal_bruto / tasa_factura
                r.total_iva_bs = r.total_iva
                r.total_iva_usd = r.total_iva / tasa_factura
                r.monto_descuento_bs = desc_bs
                r.monto_descuento_usd = desc_usd
            
            r.descuento_visual = f"$ {desc_usd:,.2f}"

    @api.depends('total', 'pago_ids.monto', 'pago_ids.moneda', 'moneda', 'tasa_aplicada', 'vuelto_entregado_usd', 'condiciones_pago', 'vuelto_pago_movil_bs')
    def _compute_estado_cuenta(self):
        for r in self:
            tasa = r.tasa_aplicada if r.tasa_aplicada > 0 else 1.0
            pagado_convertido = 0.0
            for p in r.pago_ids:
                if p.moneda == r.moneda:
                    pagado_convertido += p.monto
                elif r.moneda == 'usd' and p.moneda == 'bs':
                    pagado_convertido += (p.monto / tasa)
                elif r.moneda == 'bs' and p.moneda == 'usd':
                    pagado_convertido += (p.monto * tasa)
            
            r.pago_inicial = pagado_convertido
            
            vuelto_efectivo_convertido = r.vuelto_entregado_usd if r.moneda == 'usd' else (r.vuelto_entregado_usd * tasa)
            vuelto_pm_convertido = (r.vuelto_pago_movil_bs / tasa) if r.moneda == 'usd' else r.vuelto_pago_movil_bs
            
            vuelto_total_convertido = vuelto_efectivo_convertido + vuelto_pm_convertido
            
            if r.condiciones_pago == 'canon':
                r.saldo_pendiente = 0.0
            else:
                r.saldo_pendiente = r.total - (pagado_convertido - vuelto_total_convertido)
            
            if r.estado != 'borrador':
                r.estado = 'parcial' if r.saldo_pendiente > 0.01 else 'pagado'

class BateriaCliente(models.Model):
    _name = 'bateria.cliente'
    _description = 'Directorio de Clientes'
    _rec_name = 'name'

    name = fields.Char(string='Nombre / Razón Social', required=True)
    rif = fields.Char(string='Cédula / RIF', required=True)
    telefono = fields.Char(string='Teléfono')
    direccion = fields.Text(string='Dirección')

# =================================================================================
# 2. LÍNEAS DE PRODUCTOS
# =================================================================================
class BateriaOrdenLinea(models.Model):
    _name = 'bateria.orden.linea'
    _description = 'Líneas de la Orden'

    orden_id = fields.Many2one('bateria.orden.venta', ondelete='cascade')
    
    fecha_venta_bi = fields.Datetime(related='orden_id.fecha_creacion', store=True, string='Fecha de Venta')
    estado_venta_bi = fields.Selection(related='orden_id.estado', store=True, string='Estado Factura')

    producto_id = fields.Many2one('bateria.producto', required=False)
    requiere_serial = fields.Boolean(related='producto_id.requiere_serial')
    
    articulo_historial_id = fields.Many2one(
        'bateria.compra.linea', 
        string='🔍 Buscar en Historial (Opcional)',
        help="Selecciona un artículo comprado anteriormente para copiar su descripción y costo."
    )

    descripcion = fields.Char(string='Descripción del Artículo', required=True)
    unidad_medida_texto = fields.Char(string='Unidad de Medida', default='UNIDAD')
    cantidad = fields.Integer(default=1, required=True)

    usar_tasa_linea = fields.Boolean(string='Tasa Indiv.', default=False)
    tasa_linea = fields.Float(string='Tasa del Ítem', default=0.0)

    precio_usd = fields.Float(string='Precio ($)', required=True, default=0.0)
    precio_bs = fields.Float(string='Precio (Bs)', compute='_compute_precios_bs', inverse='_inverse_precios_bs', store=True)
    
    subtotal_usd = fields.Float(string='Total ($)', compute='_compute_subtotales_duales', store=True)
    subtotal_bs = fields.Float(string='Total (Bs)', compute='_compute_subtotales_duales', store=True)
    aplica_iva = fields.Boolean(string='IVA 16%', default=False)
    monto_iva = fields.Float(string='Monto IVA', compute='_compute_subtotales_duales', store=True)
    subtotal = fields.Float(string='Subtotal Base', compute='_compute_subtotales_duales', store=True)
    moneda = fields.Selection(related='orden_id.moneda', store=True)

    saltar_regla_antiguedad = fields.Boolean(string='Permiso Admin (Vender Nueva)', default=False, copy=False)

    serial_ids = fields.Many2many(
        'bateria.serial', 
        string='Seriales a Entregar', 
        domain="[('producto_id', '=', producto_id), ('estado', '=', 'disponible'), ('ubicacion_id.nombre_completo', 'ilike', 'racksito')]"
    )
    
    seriales_masivos = fields.Text(string='Pegar Seriales (Histórico)', help="Pega aquí tu lista de 160 seriales.")
    
    costo_unitario_usd = fields.Float(string="Costo Referencia ($)", default=0.0)
    ganancia_usd = fields.Float(string='Ganancia Neta ($)', compute='_compute_ganancia', store=True)

    @api.depends('cantidad', 'precio_usd', 'costo_unitario_usd')
    def _compute_ganancia(self):
        for l in self:
            l.ganancia_usd = (l.precio_usd - l.costo_unitario_usd) * l.cantidad

    @api.onchange('articulo_historial_id')
    def _onchange_articulo_historial(self):
        if self.articulo_historial_id:
            desc = self.articulo_historial_id.descripcion_proveedor
            if not desc and self.articulo_historial_id.producto_maestro_id:
                desc = self.articulo_historial_id.producto_maestro_id.nombre
            elif not desc and hasattr(self.articulo_historial_id, 'gasto_id') and self.articulo_historial_id.gasto_id:
                desc = self.articulo_historial_id.gasto_id.name
            
            if desc:
                self.descripcion = desc
            
            if hasattr(self.articulo_historial_id, 'unidad_medida') and self.articulo_historial_id.unidad_medida:
                self.unidad_medida_texto = self.articulo_historial_id.unidad_medida
                
            self.costo_unitario_usd = self.articulo_historial_id.precio_usd

    info_disponibilidad = fields.Text(string='📍 Disponibilidad', compute='_compute_info_disponibilidad')

    @api.depends('producto_id', 'cantidad', 'orden_id.traslado_estado')
    def _compute_info_disponibilidad(self):
        for l in self:
            if not l.producto_id:
                l.info_disponibilidad = ""
                continue
                
            if not l.producto_id.requiere_serial:
                ingresos = sum(self.env['bateria.inventario'].search([('producto_id', '=', l.producto_id.id), ('tipo_movimiento', '=', 'ingreso')]).mapped('cantidad'))
                salidas = sum(self.env['bateria.inventario'].search([('producto_id', '=', l.producto_id.id), ('tipo_movimiento', '=', 'salida')]).mapped('cantidad'))
                stock = ingresos - salidas
                l.info_disponibilidad = f"📦 Stock General (Sin Serial): {stock} unidades"
                continue
            
            qty_racksito = self.env['bateria.serial'].search_count([
                ('producto_id', '=', l.producto_id.id),
                ('estado', '=', 'disponible'),
                ('ubicacion_id.nombre_completo', 'ilike', 'racksito')
            ])
            
            seriales_otros = self.env['bateria.serial'].search([
                ('producto_id', '=', l.producto_id.id),
                ('estado', '=', 'disponible'),
                '!', ('ubicacion_id.nombre_completo', 'ilike', 'racksito')
            ])
            qty_otros = len(seriales_otros)
            
            desglose_str = ""
            if qty_otros > 0:
                conteo = {}
                for s in seriales_otros:
                    loc = s.ubicacion_id.nombre_completo or 'Galpón'
                    conteo[loc] = conteo.get(loc, 0) + 1
                desglose_str = ", ".join([f"{v} en {k}" for k, v in conteo.items()])
            else:
                desglose_str = "0"

            if l.cantidad > qty_racksito:
                l.info_disponibilidad = f"⚠️ Faltan en Racksito (Hay {qty_racksito})\n📦 En Galpones: {qty_otros} (Detalle: {desglose_str})"
            else:
                l.info_disponibilidad = f"✅ En Racksito: {qty_racksito} (Suficientes)\n📦 En Galpones: {qty_otros} (Detalle: {desglose_str})"

    @api.onchange('producto_id', 'cantidad', 'orden_id.es_venta_historica')
    def _onchange_alerta_stock(self):
        if not self.producto_id or not self.producto_id.requiere_serial or self.orden_id.es_venta_historica:
            return
        qty_racksito = self.env['bateria.serial'].search_count([
            ('producto_id', '=', self.producto_id.id),
            ('estado', '=', 'disponible'),
            ('ubicacion_id.nombre_completo', 'ilike', 'racksito')
        ])
        if self.cantidad > qty_racksito:
            mensaje = f"🛑 ¡ALERTA!\nIntentas cotizar {self.cantidad} unidades, pero solo tienes {qty_racksito} en RACKSITO.\n\n➡️ Recuerda solicitar un traslado al administrador antes de venderla."
            return {'warning': {'title': '⚠️ Requiere Traslado', 'message': mensaje}}

    precio_unit_bs = fields.Float(string='Precio Unit (Bs) Nuevo')
    subtotal_ref = fields.Float(string='Subtotal Ref', compute='_compute_subtotales_duales', store=True)

    @api.onchange('producto_id', 'cantidad', 'orden_id.es_venta_historica')
    def _onchange_verificar_stock(self):
        if not self.producto_id:
            self.info_disponibilidad = ""
            return
            
        if not self.producto_id.requiere_serial:
            ingresos = sum(self.env['bateria.inventario'].search([('producto_id', '=', self.producto_id.id), ('tipo_movimiento', '=', 'ingreso')]).mapped('cantidad'))
            salidas = sum(self.env['bateria.inventario'].search([('producto_id', '=', self.producto_id.id), ('tipo_movimiento', '=', 'salida')]).mapped('cantidad'))
            stock = ingresos - salidas
            self.info_disponibilidad = f"📦 Stock General (Sin Serial): {stock} unidades"
            return

        seriales_racksito = self.env['bateria.serial'].search([
            ('producto_id', '=', self.producto_id.id),
            ('estado', '=', 'disponible'),
            ('ubicacion_id.nombre_completo', 'ilike', 'racksito')
        ])
        qty_racksito = len(seriales_racksito)

        seriales_otros = self.env['bateria.serial'].search([
            ('producto_id', '=', self.producto_id.id),
            ('estado', '=', 'disponible'),
            '!', ('ubicacion_id.nombre_completo', 'ilike', 'racksito')
        ])
        qty_otros = len(seriales_otros)

        desglose_str = ""
        if qty_otros > 0:
            conteo = {}
            for s in seriales_otros:
                loc = s.ubicacion_id.nombre_completo or 'Galpón'
                conteo[loc] = conteo.get(loc, 0) + 1
            desglose_str = ", ".join([f"{v} en {k}" for k, v in conteo.items()])
        else:
            desglose_str = "0"

        self.info_disponibilidad = f"✅ En Racksito: {qty_racksito}\n📦 En Galpones: {qty_otros} (Detalle: {desglose_str})"

        if self.cantidad > qty_racksito and not self.orden_id.es_venta_historica:
            mensaje_alerta = (
                f"🛑 ¡ALERTA DE INVENTARIO!\n\n"
                f"Estás cotizando {self.cantidad} unidades, pero solo tienes {qty_racksito} en el RACKSITO.\n\n"
                f"🔍 Tienes {qty_otros} baterías en estas ubicaciones:\n"
                f"{desglose_str}\n\n"
                f"➡️ ACCIÓN REQUERIDA: Debes solicitar un traslado de mercancía al Racksito antes de despachar esta venta."
            )
            return {
                'warning': {
                    'title': '⚠️ Se requiere Traslado a Racksito',
                    'message': mensaje_alerta
                }
            }

    @api.onchange('serial_ids')
    def _onchange_serials(self):
        if self.serial_ids and self.producto_id and self.producto_id.requiere_serial:
            self.cantidad = len(self.serial_ids)

    texto_tasa = fields.Char(string='Tasa Aplicada', compute='_compute_texto_tasa')

    @api.depends('orden_id.moneda_referencia', 'orden_id.tasa_aplicada', 'usar_tasa_linea', 'tasa_linea')
    def _compute_texto_tasa(self):
        for l in self:
            if l.usar_tasa_linea and l.tasa_linea > 0:
                l.texto_tasa = f"Tasa Propia ({l.tasa_linea})"
            elif l.orden_id.moneda_referencia == 'eur':
                l.texto_tasa = f"Tasa EURO ({l.orden_id.tasa_aplicada})"
            elif l.orden_id.moneda_referencia == 'usdt':
                l.texto_tasa = f"Tasa USDT ({l.orden_id.tasa_aplicada})"
            else:
                l.texto_tasa = f"Tasa BCV ({l.orden_id.tasa_aplicada})"
    
    @api.onchange('producto_id', 'orden_id.tarifa_id')
    def _onchange_producto(self):
        if self.producto_id:
            self.descripcion = self.producto_id.nombre
            self.costo_unitario_usd = self.producto_id.costo_standard_usd
            
            precio_base_divisa = self.producto_id.precio_base_usd
            
            if self.orden_id.tarifa_id:
                regla = self.env['bateria.producto.tarifa'].search([
                    ('producto_id', '=', self.producto_id.id),
                    ('tarifa_id', '=', self.orden_id.tarifa_id.id)
                ], limit=1)
                if regla:
                    if regla.moneda == 'usd': 
                        precio_base_divisa = regla.precio
                    else: 
                        tasa_g = float(self.env['ir.config_parameter'].sudo().get_param('bateria.tasa_usdt', default='1.0'))
                        precio_base_divisa = regla.precio / tasa_g if tasa_g > 0 else regla.precio
            
            tasa = self.tasa_linea if (self.usar_tasa_linea and self.tasa_linea > 0) else (self.orden_id.tasa_aplicada if self.orden_id.tasa_aplicada > 0 else 1.0)
            
            self.precio_usd = precio_base_divisa
            self.precio_bs = precio_base_divisa * tasa

    @api.depends('precio_usd', 'orden_id.tasa_aplicada', 'usar_tasa_linea', 'tasa_linea')
    def _compute_precios_bs(self):
        for l in self:
            if l.usar_tasa_linea and l.tasa_linea > 0:
                tasa = l.tasa_linea
            else:
                tasa = l.orden_id.tasa_aplicada if (hasattr(l.orden_id, 'tasa_aplicada') and l.orden_id.tasa_aplicada > 0) else 1.0
            l.precio_bs = l.precio_usd * tasa

    def _inverse_precios_bs(self):
        for l in self:
            if l.usar_tasa_linea and l.tasa_linea > 0:
                tasa = l.tasa_linea
            else:
                tasa = l.orden_id.tasa_aplicada if (hasattr(l.orden_id, 'tasa_aplicada') and l.orden_id.tasa_aplicada > 0) else 1.0
            l.precio_usd = l.precio_bs / tasa if tasa > 0 else 0.0

    @api.onchange('precio_usd')
    def _onchange_sync_bs_venta(self):
        tasa = self.tasa_linea if (self.usar_tasa_linea and self.tasa_linea > 0) else (self.orden_id.tasa_aplicada or 1.0)
        self.precio_bs = self.precio_usd * tasa

    @api.onchange('precio_bs')
    def _onchange_sync_usd_venta(self):
        tasa = self.tasa_linea if (self.usar_tasa_linea and self.tasa_linea > 0) else (self.orden_id.tasa_aplicada or 1.0)
        if tasa > 0:
            self.precio_usd = self.precio_bs / tasa

    @api.depends('cantidad', 'precio_usd', 'precio_bs', 'aplica_iva', 'orden_id.moneda', 'orden_id.tasa_aplicada', 'usar_tasa_linea', 'tasa_linea')
    def _compute_subtotales_duales(self):
        for l in self:
            l.subtotal_usd = l.cantidad * l.precio_usd
            l.subtotal_bs = l.cantidad * l.precio_bs
            
            precio_base = l.precio_usd if l.orden_id.moneda == 'usd' else l.precio_bs
            sub_bruto = l.cantidad * precio_base
            
            l.subtotal = sub_bruto
            l.monto_iva = sub_bruto * 0.16 if l.aplica_iva else 0.0
            
            if l.usar_tasa_linea and l.tasa_linea > 0:
                tasa_nueva = l.tasa_linea
            else:
                tasa_nueva = l.orden_id.tasa_aplicada if (hasattr(l.orden_id, 'tasa_aplicada') and l.orden_id.tasa_aplicada > 0) else 1.0
                
            l.subtotal_ref = l.subtotal_bs / tasa_nueva if tasa_nueva > 0 else l.subtotal_bs

# =================================================================================
# 3. DETALLE DE BILLETES DE VUELTO
# =================================================================================
class BateriaVueltoBillete(models.Model):
    _name = 'bateria.vuelto.billete'
    _description = 'Detalle de Billetes para Vuelto'

    orden_id = fields.Many2one('bateria.orden.venta', string='Orden', ondelete='cascade')
    
    denominacion = fields.Selection([
        ('1', 'Billete de $1'),
        ('5', 'Billete de $5'),
        ('10', 'Billete de $10'),
        ('20', 'Billete de $20'),
        ('50', 'Billete de $50'),
        ('100', 'Billete de $100')
    ], string='Denominación', required=True)
    
    cantidad = fields.Integer(string='Cantidad', default=1, required=True)
    seriales = fields.Char(string='Seriales', required=True, help="Ej: AB123456789")
    subtotal = fields.Float(string='Total ($)', compute='_compute_subtotal', store=True)

    @api.depends('denominacion', 'cantidad')
    def _compute_subtotal(self):
        for r in self:
            val = float(r.denominacion) if r.denominacion else 0.0
            r.subtotal = val * r.cantidad

# =================================================================================
# REINTEGROS Y DEVOLUCIONES
# =================================================================================
class BateriaReintegro(models.Model):
    _name = 'bateria.reintegro'
    _description = 'Reintegros y Devoluciones'
    _rec_name = 'name'
    _order = 'fecha desc, id desc'

    name = fields.Char(string='Referencia', required=True, copy=False, readonly=True, default='Nuevo')
    fecha = fields.Date(string='Fecha', default=fields.Date.context_today, required=True)
    
    cliente_id = fields.Many2one('bateria.cliente', string='Cliente', required=True)
    
    es_sistema_anterior = fields.Boolean(string='¿Viene del sistema viejo / sin factura en Odoo?', default=False)
    orden_venta_id = fields.Many2one('bateria.orden.venta', string='Factura de Origen', domain="[('cliente_id', '=', cliente_id), ('estado', '!=', 'borrador')]")
    
    ubicacion_destino_id = fields.Many2one('bateria.ubicacion', string='Almacén de Reingreso', required=True)
    
    motivo = fields.Text(string='Motivo de la Devolución', required=True, help="Explica por qué se realiza el reintegro y qué acordó el cliente.")
    
    ingresar_chatarra = fields.Boolean(
        string='♻️ ¿Añadir al Inventario de Chatarras?', 
        compute='_compute_ingresar_chatarra', 
        store=True, 
        readonly=False,
        help="Si la factura no es Canon, se marca automáticamente para ir a Chatarra."
    )

    estado = fields.Selection([
        ('borrador', 'Borrador'),
        ('procesado', 'Reintegro Procesado')
    ], string='Estado', default='borrador')

    linea_ids = fields.One2many('bateria.reintegro.linea', 'reintegro_id', string='Baterías a Devolver')

    @api.depends('orden_venta_id.condiciones_pago')
    def _compute_ingresar_chatarra(self):
        for r in self:
            if r.orden_venta_id and r.orden_venta_id.condiciones_pago == 'canon':
                r.ingresar_chatarra = False
            else:
                r.ingresar_chatarra = True

    @api.onchange('orden_venta_id')
    def _onchange_orden(self):
        if self.orden_venta_id:
            self.cliente_id = self.orden_venta_id.cliente_id.id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('bateria.reintegro.seq') or 'DEV-0000'
        return super(BateriaReintegro, self).create(vals_list)

    def action_procesar_reintegro(self):
        for r in self:
            if not r.linea_ids:
                raise UserError("Debes agregar al menos una batería para procesar el reintegro.")
            
            for linea in r.linea_ids:
                estado_serial = 'chatarra' if r.ingresar_chatarra else 'disponible'
                
                if r.es_sistema_anterior:
                    if not linea.serial_manual:
                        raise UserError("Debes escribir el serial de la batería vieja.")
                    
                    existente = self.env['bateria.serial'].search([('nombre', '=', linea.serial_manual)], limit=1)
                    if existente:
                        existente.write({
                            'estado': estado_serial if r.ingresar_chatarra else 'disponible',
                            'ubicacion_id': r.ubicacion_destino_id.id,
                            'orden_venta_id': False
                        })
                    else:
                        self.env['bateria.serial'].create({
                            'nombre': linea.serial_manual,
                            'producto_id': linea.producto_id.id,
                            'ubicacion_id': r.ubicacion_destino_id.id,
                            'estado': estado_serial if r.ingresar_chatarra else 'disponible',
                            'fecha_ingreso': fields.Date.context_today(self)
                        })
                    serial_texto = linea.serial_manual
                else:
                    if not linea.serial_id:
                        raise UserError("Debes seleccionar el serial que se está devolviendo.")
                    
                    linea.serial_id.write({
                        'estado': estado_serial if r.ingresar_chatarra else 'disponible',
                        'ubicacion_id': r.ubicacion_destino_id.id,
                        'orden_venta_id': False
                    })
                    serial_texto = linea.serial_id.nombre

                self.env['bateria.inventario'].create({
                    'fecha': fields.Datetime.now(),
                    'tipo_movimiento': 'entrada',
                    'producto_id': linea.producto_id.id,
                    'cantidad': 1,
                    'ubicacion_id': r.ubicacion_destino_id.id,
                    'nota': f"DEVOLUCIÓN Ref: {r.name} | Motivo: {r.motivo} | Serial: {serial_texto} | A Chatarra: {'SÍ' if r.ingresar_chatarra else 'NO'}"
                })
            
            if r.ingresar_chatarra:
                desc_chatarra = " | ".join([l.producto_id.nombre for l in r.linea_ids])
                self.env['bateria.chatarra'].create({
                    'orden_venta_id': r.orden_venta_id.id if r.orden_venta_id else False,
                    'cliente_id': r.cliente_id.id,
                    'descripcion': f"Ingresada por Reintegro: {desc_chatarra}",
                    'cantidad': len(r.linea_ids),
                    'fecha': r.fecha
                })
                
            r.estado = 'procesado'
            
        msg = '¡Reintegro procesado! Las baterías fueron sumadas al inventario de Chatarras.' if self.ingresar_chatarra else '¡Reintegro procesado! El serial volvió a estar Disponible en el almacén.'
        return {
            'effect': {
                'fadeout': 'slow',
                'message': msg,
                'type': 'rainbow_man',
            }
        }

class BateriaReintegroLinea(models.Model):
    _name = 'bateria.reintegro.linea'
    _description = 'Línea de Reintegro'

    reintegro_id = fields.Many2one('bateria.reintegro', ondelete='cascade')
    producto_id = fields.Many2one('bateria.producto', string='Modelo de Batería', required=True)
    
    es_sistema_anterior = fields.Boolean(related='reintegro_id.es_sistema_anterior')
    orden_venta_id = fields.Many2one(related='reintegro_id.orden_venta_id')
    
    serial_id = fields.Many2one('bateria.serial', string='Serial (En Odoo)')
    serial_manual = fields.Char(string='Serial (Físico / Sistema Viejo)')