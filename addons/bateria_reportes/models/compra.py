from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class BateriaUbicacionExt(models.Model):
    _inherit = 'bateria.ubicacion'
    
    categoria_almacen = fields.Selection([
        ('baterias', '🔋 Galpón de Baterías'),
        ('restaurante', '🍽️ Restaurante'),
        ('beisbol', '⚾ Academia de Béisbol'),
        ('general', '📦 Uso General / Otros')
    ], string="Categoría de Almacén", default='baterias')

class BateriaCentroCosto(models.Model):
    _name = 'bateria.centro.costo'
    _description = 'Centro de Costo / Gastos'
    _rec_name = 'name'

    name = fields.Char(string='Nombre del Centro de Costo', required=True)
    codigo = fields.Char(string='Código / Referencia')
    active = fields.Boolean(string='Activo', default=True)

class BateriaCompra(models.Model):
    _name = 'bateria.compra'
    _description = 'Pedido de Compra (Corporativo)'
    _rec_name = 'name'

    company_id = fields.Many2one('res.company', string='Compañía', required=True, default=lambda self: self.env.company)

    name = fields.Char(string='Referencia', required=True, copy=False, readonly=True, default='Nuevo Presupuesto')
    fecha = fields.Date(string='Fecha de Compra', default=fields.Date.context_today)

    tipo_documento = fields.Selection([
        ('nota_entrega', 'Nota de Entrega / Recibo'),
        ('factura', 'Factura Fiscal')
    ], string='Tipo de Documento', required=True, default='nota_entrega')
    
    
    proveedor_id = fields.Many2one('bateria.proveedor', string='Proveedor', required=True)
    rif = fields.Char(related='proveedor_id.rif', readonly=True)
    
    estado = fields.Selection([
        ('borrador', '📄 Presupuesto (RFQ)'),
        ('confirmado', '🛒 Pedido Confirmado'),
        ('recibido', '📦 Mercancía Recibida'),
        ('facturado', '🧾 Facturado (Por Pagar)'),
        ('pagado', '✅ Compra Pagada'), 
        ('cancelado', '🚫 Cancelado')
    ], string='Estado', default='borrador')
    
    linea_ids = fields.One2many('bateria.compra.linea', 'compra_id', string='Detalle de Productos')
    
    pago_ids = fields.One2many('bateria.compra.pago', 'compra_id', string='Historial de Pagos')
    monto_pagado = fields.Float(string='Total Abonado', compute='_compute_pagos', store=True)
    saldo_pendiente = fields.Float(string='Saldo Pendiente', compute='_compute_pagos', store=True)
    
    descuento_global = fields.Float(string='Descuento Global (Monto)', default=0.0, help="Descuento en dinero aplicado al total de la compra")
    referencia_factura = fields.Char(string='Nro. Factura / Recibo del Proveedor', help="Coloque aquí el número de factura que le entregó la tienda o proveedor", copy=False)
    asiento_id = fields.Many2one('bateria.asiento', string='Asiento Contable Generado', readonly=True)
    
    def _get_tasa_bcv_actual(self):
        tasa = self.env['ir.config_parameter'].sudo().get_param('bateria.tasa_usdt', default='1.0')
        return float(tasa)

    moneda = fields.Selection([('usd', 'USD'), ('bs', 'Bs')], required=True, default='usd')
    tasa_bcv = fields.Float(string='Tasa BCV', default=_get_tasa_bcv_actual)
    tasa_cambio = fields.Float(string='Tasa Cambio')
    usar_tasa_personalizada = fields.Boolean()
    
    moneda_referencia = fields.Selection([
        ('usdt', 'USDT (Binance/Paralelo)'), 
        ('usd', 'Dólar BCV'), 
        ('eur', 'Euro BCV')
    ], string='Tasa Referencia', default='usdt', required=True)
    
    tasa_aplicada = fields.Float(string='Tasa del Día', compute='_compute_tasa_aplicada', store=True)
    
    base_imponible = fields.Float(string='Base Imponible', compute='_compute_totales', store=True)
    base_exenta = fields.Float(string='Base Exenta', compute='_compute_totales', store=True)
    monto_base_compra = fields.Float(string='Total Base', compute='_compute_totales', store=True)
    
    monto_iva = fields.Float(string='IVA (16%)', compute='_compute_totales', store=True)
    total = fields.Float(string='Total Factura (Bruto)', compute='_compute_totales', store=True)

    porcentaje_retencion_iva = fields.Selection([
        ('0', '0%'),
        ('75', '75%'),
        ('100', '100%')
    ], string='% Retención IVA', default='0')
    monto_retencion_iva = fields.Float(string='Retención IVA (-)', compute='_compute_totales', store=True)
    comprobante_retencion_iva = fields.Char(string='Comprobante Ret. IVA')

    porcentaje_retencion_islr = fields.Float(string='% Retención ISLR', default=0.0, help="Ejemplo: 2 para 2%")
    monto_retencion_islr = fields.Float(string='Retención ISLR (-)', compute='_compute_totales', store=True)
    comprobante_retencion_islr = fields.Char(string='Comprobante Ret. ISLR')

    total_neto = fields.Float(string='Total a Pagar (Neto)', compute='_compute_totales', store=True)

    total_global_bs = fields.Float(string='Total Neto Bs', compute='_compute_totales_globales', store=True)
    total_global_usd = fields.Float(string='Total Neto $', compute='_compute_totales_globales', store=True)
    texto_conversion = fields.Char(string='Conv', compute='_compute_totales_globales', store=True)

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

    @api.onchange('moneda_referencia', 'usar_tasa_personalizada', 'tasa_cambio')
    def _onchange_forzar_actualizacion_totales(self):
        if self.usar_tasa_personalizada and self.tasa_cambio > 0:
            self.tasa_bcv = self.tasa_cambio
        else:
            if self.moneda_referencia == 'usdt': param = 'bateria.tasa_usdt'
            elif self.moneda_referencia == 'usd': param = 'bateria.tasa_bcv_usd'
            else: param = 'bateria.tasa_bcv_eur'
            self.tasa_bcv = float(self.env['ir.config_parameter'].sudo().get_param(param, default='1.0'))

    def action_actualizar_tasa_bcv_manual(self):
        try:
            self.env['bateria.bcv.scraper'].actualizar_tasas_completas()
        except:
            pass
        self._compute_tasa_aplicada()

    @api.depends('total_neto', 'moneda', 'tasa_aplicada')
    def _compute_totales_globales(self):
        for r in self:
            tasa = r.tasa_aplicada if r.tasa_aplicada > 0 else 1.0
            if r.moneda == 'usd':
                r.total_global_usd = r.total_neto 
                r.total_global_bs = r.total_neto * tasa
                r.texto_conversion = f"{r.total_global_bs:,.2f} Bs"
            else:
                r.total_global_bs = r.total_neto 
                r.total_global_usd = r.total_neto / tasa
                r.texto_conversion = f"{r.total_global_usd:,.2f} $"

    @api.depends('linea_ids.subtotal', 'linea_ids.aplica_iva', 'porcentaje_retencion_iva', 'porcentaje_retencion_islr', 'descuento_global')
    def _compute_totales(self):
        for rec in self:
            base_imp_bruta = sum(linea.subtotal for linea in rec.linea_ids if linea.aplica_iva)
            base_exe_bruta = sum(linea.subtotal for linea in rec.linea_ids if not linea.aplica_iva)
            
            total_base_bruta = base_imp_bruta + base_exe_bruta
            
            if total_base_bruta > 0 and rec.descuento_global > 0:
                prop_imp = base_imp_bruta / total_base_bruta
                prop_exe = base_exe_bruta / total_base_bruta
                
                desc_imp = rec.descuento_global * prop_imp
                desc_exe = rec.descuento_global * prop_exe
            else:
                desc_imp = 0.0
                desc_exe = 0.0
                
            rec.base_imponible = max(0.0, base_imp_bruta - desc_imp)
            rec.base_exenta = max(0.0, base_exe_bruta - desc_exe)
            rec.monto_base_compra = rec.base_imponible + rec.base_exenta
            
            iva = rec.base_imponible * 0.16
            rec.monto_iva = iva
            rec.total = rec.monto_base_compra + iva
            
            porc_iva = float(rec.porcentaje_retencion_iva) / 100.0
            ret_iva = iva * porc_iva
            rec.monto_retencion_iva = ret_iva
            
            ret_islr = rec.monto_base_compra * (rec.porcentaje_retencion_islr / 100.0)
            rec.monto_retencion_islr = ret_islr
            
            rec.total_neto = rec.total - ret_iva - ret_islr

    def action_agregar_iva(self):
        for r in self: 
            for linea in r.linea_ids:
                linea.aplica_iva = True

    def action_quitar_iva(self):
        for r in self: 
            for linea in r.linea_ids:
                linea.aplica_iva = False

    @api.depends('pago_ids.monto', 'pago_ids.moneda', 'total_global_usd', 'total_global_bs', 'moneda', 'tasa_aplicada')
    def _compute_pagos(self):
        for r in self:
            pagado_convertido = 0.0
            for p in r.pago_ids:
                if p.moneda == r.moneda:
                    pagado_convertido += p.monto
                else:
                    tasa = r.tasa_aplicada if r.tasa_aplicada > 0 else 1.0
                    if r.moneda == 'usd' and p.moneda == 'bs':
                        pagado_convertido += p.monto / tasa
                    elif r.moneda == 'bs' and p.moneda == 'usd':
                        pagado_convertido += p.monto * tasa

            r.monto_pagado = pagado_convertido
            total_base = r.total_global_usd if r.moneda == 'usd' else r.total_global_bs
            r.saldo_pendiente = total_base - pagado_convertido
            
            if r.saldo_pendiente <= 0 and total_base > 0 and r.estado in ('confirmado', 'recibido', 'facturado'):
                r.estado = 'pagado'
                
            if r.cuenta_pagar_id:
                r.cuenta_pagar_id.monto_pagado = pagado_convertido
                if r.saldo_pendiente <= 0:
                    r.cuenta_pagar_id.estado = 'pagado'

    ubicacion_id = fields.Many2one('bateria.ubicacion', string='Almacén / Sede de Destino', required=True)
    centro_costo_id = fields.Many2one('bateria.centro.costo', string='Centro de Costo', required=True)
    
    empresa_compra = fields.Selection([
        ('don_juan', 'Corporación de Servicios Múltiples Don Juan, C.A.'),
        ('juan_andres', 'Juan Andres Cafe 33, C.A.'),
        ('jjs_2021', 'Inversiones J.J.S 2021, C.A.'),
        ('zolmala_2000', 'Inversiones Zolmala 2000, C.A.'),
        ('primos_3021', 'Inversiones Los Primos 3021, C.A.'),
        ('juanes_2021', 'Cooperativa Los Juanes 2021, C.A.'),
        ('primos_3000', 'Inversiones Los Primos 3000 & Asociados, C.A.'),
        ('dr_battery', 'Dr Battery 33, C.A.'),
        ('carpimachado', 'INVERSIONES CARPIMACHADO'),
        ('car_car', 'INVERSIONES CAR-CAR 0473, C.A.'),
        ('super_car', 'INVERSIONES SUPERCAR 1102 C.A.'),
        ('personal', 'Cuenta Personal / Directiva')
    ], string='Empresa que Compra', required=True, default='don_juan')

    condicion_pago = fields.Selection([
        ('contado', 'De Contado (Pago Inmediato)'),
        ('credito_15', 'Por Pagar (Crédito a 15 Días)'),
        ('credito_30', 'Por Pagar (Crédito a 30 Días)'),
        ('credito_45', 'Por Pagar (Crédito a 45 Días)'),
    ], string='Condición de Pago', default='contado', required=True)
    
    cuenta_pagar_id = fields.Many2one('bateria.cuenta.pagar', string='Cuenta por Pagar', readonly=True)
    albaran_entrada_id = fields.Many2one('bateria.recepcion', string='Recepción de Almacén', readonly=True)

    def action_confirmar_pedido(self):
        for compra in self:
            if not compra.linea_ids:
                raise UserError("No puedes confirmar un pedido vacío.")
                
            if compra.name == 'Nuevo Presupuesto':
                compra.name = self.env['ir.sequence'].next_by_code('bateria.compra.seq') or f'PO-{compra.id}'
            
            lineas_recepcion = []
            for linea in compra.linea_ids:
                if not linea.producto_maestro_id and not linea.gasto_id:
                    raise UserError("Debes seleccionar una Batería o escribir un Gasto en todas las líneas.")
                
                if linea.gasto_id and linea.precio_usd > 0:
                    linea.gasto_id.precio_referencia_usd = linea.precio_usd

                if linea.producto_maestro_id:
                    tarifa = self.env['bateria.proveedor.tarifa'].search([
                        ('proveedor_id', '=', compra.proveedor_id.id),
                        ('producto_id', '=', linea.producto_maestro_id.id)
                    ], limit=1)
                    if tarifa:
                        tarifa.precio = linea.precio_usd
                    else:
                        self.env['bateria.proveedor.tarifa'].create({
                            'proveedor_id': compra.proveedor_id.id,
                            'producto_id': linea.producto_maestro_id.id,
                            'precio': linea.precio_usd
                        })
                    lineas_recepcion.append((0, 0, {
                        'producto_id': linea.producto_maestro_id.id,
                        'cantidad_demandada': linea.cantidad,
                    }))
                    
                # 👇 LÓGICA DE INTEGRACIÓN CON LA FLOTA VEHICULAR 👇
                if linea.es_para_flota and linea.vehiculo_id and not linea.servicio_flota_id:
                    desc = linea.descripcion_proveedor or (linea.producto_maestro_id.nombre if linea.producto_maestro_id else (linea.gasto_id.name if linea.gasto_id else 'Repuesto de Flota'))
                    nuevo_servicio = self.env['bateria.vehiculo.servicio'].create({
                        'vehiculo_id': linea.vehiculo_id.id,
                        'tipo_servicio': 'mantenimiento',
                        'fecha': compra.fecha,
                        'km_anterior': linea.vehiculo_id.kilometraje_actual,
                        'km_actual': linea.vehiculo_id.kilometraje_actual, # El kilometraje se mantiene igual al comprar repuesto
                        'costo_total': linea.subtotal_usd,
                        'notas': f"Compra de Insumo/Repuesto (Ref Compras: {compra.name}) - {desc}"
                    })
                    linea.servicio_flota_id = nuevo_servicio.id
            
            if lineas_recepcion:
                nuevo_albaran = self.env['bateria.recepcion'].create({
                    'compra_id': compra.id,
                    'ubicacion_id': compra.ubicacion_id.id,
                    'linea_ids': lineas_recepcion
                })
                compra.albaran_entrada_id = nuevo_albaran.id
                
            compra.estado = 'confirmado'

    def action_recibir_mercancia(self):
        for compra in self:
            if not compra.albaran_entrada_id:
                compra.estado = 'recibido'
                return {
                    'effect': {
                        'fadeout': 'slow',
                        'message': 'Gasto / Servicio marcado como recibido.',
                        'type': 'rainbow_man',
                    }
                }
            return {
                'type': 'ir.actions.act_window',
                'name': 'Validar Recepción de Almacén',
                'res_model': 'bateria.recepcion',
                'res_id': compra.albaran_entrada_id.id,
                'view_mode': 'form',
                'target': 'current',
            }

    def action_crear_factura(self):
        for compra in self:
            if compra.estado not in ('recibido', 'pagado'): raise UserError("Debes recibir la compra antes de facturar.")
                
            if not compra.cuenta_pagar_id:
                monto_deuda = compra.total_global_usd if compra.moneda == 'usd' else compra.total_global_bs
                cxp = self.env['bateria.cuenta.pagar'].create({
                    'name': f"Ref: {compra.name}", 'fecha': compra.fecha, 'proveedor': compra.proveedor_id.nombre_empresa or 'Desconocido',
                    'concepto': f"Compra: {compra.centro_costo_id.name} - {compra.name}", 'moneda': compra.moneda,
                    'monto_total': monto_deuda, 'monto_pagado': compra.monto_pagado, 'condicion_pago': compra.condicion_pago,
                })
                compra.cuenta_pagar_id = cxp.id
            
            # 👇 NUEVO: CREAR ASIENTO CONTABLE AUTOMÁTICO
            if not compra.asiento_id:
                diario = self.env['bateria.diario'].search([('tipo', '=', 'compra')], limit=1)
                if diario:
                    c_cxp = self.env['bateria.cuenta.contable'].search([('name', 'ilike', 'por Pagar')], limit=1)
                    c_inv = self.env['bateria.cuenta.contable'].search([('name', 'ilike', 'Inventario')], limit=1) or c_cxp
                    c_iva = self.env['bateria.cuenta.contable'].search([('name', 'ilike', 'IVA')], limit=1) or c_cxp
                    
                    asiento = self.env['bateria.asiento'].create({
                        'fecha': compra.fecha, 'referencia': f"Factura: {compra.name}", 'diario_id': diario.id, 'estado': 'asentado'
                    })
                    if compra.monto_base_compra > 0:
                        self.env['bateria.apunte'].create({'asiento_id': asiento.id, 'cuenta_id': c_inv.id, 'nombre': "Inventario/Compra", 'debe': compra.monto_base_compra, 'haber': 0.0})
                    if compra.monto_iva > 0:
                        self.env['bateria.apunte'].create({'asiento_id': asiento.id, 'cuenta_id': c_iva.id, 'nombre': "IVA Crédito Fiscal", 'debe': compra.monto_iva, 'haber': 0.0})
                    self.env['bateria.apunte'].create({'asiento_id': asiento.id, 'cuenta_id': c_cxp.id, 'cliente_id': compra.proveedor_id.id, 'nombre': "Cuentas por Pagar", 'debe': 0.0, 'haber': compra.total})
                    compra.asiento_id = asiento.id

            compra.estado = 'pagado' if compra.saldo_pendiente <= 0 else 'facturado'

    def action_cancelar(self):
        for compra in self:
            if compra.estado in ('facturado', 'pagado'):
                raise UserError("No puedes cancelar una compra facturada o pagada.")
            if compra.albaran_entrada_id and compra.albaran_entrada_id.estado == 'listo':
                compra.albaran_entrada_id.estado = 'cancelado'
                
            # Eliminamos el registro en la flota si se cancela la compra
            for linea in compra.linea_ids:
                if linea.servicio_flota_id:
                    linea.servicio_flota_id.unlink()
                    
            compra.estado = 'cancelado'


class BateriaCompraLinea(models.Model):
    _name = 'bateria.compra.linea'
    _description = 'Línea de Pedido de Compra'

    compra_id = fields.Many2one('bateria.compra', string='Compra', ondelete='cascade')
    
    fecha_compra = fields.Date(related='compra_id.fecha', store=True, string='Fecha')
    proveedor_id = fields.Many2one(related='compra_id.proveedor_id', store=True, string='Proveedor')
    centro_costo_id = fields.Many2one(related='compra_id.centro_costo_id', store=True, string='Centro de Costo')
    tasa_aplicada = fields.Float(related='compra_id.tasa_aplicada', store=True, string='Tasa')
    estado_compra = fields.Selection(related='compra_id.estado', store=True, string='Estado')

    imagen_producto = fields.Binary(string='Foto / Referencia', attachment=True)
    
    producto_maestro_id = fields.Many2one('bateria.producto', string='Catálogo Baterías', required=False)
    gasto_id = fields.Many2one('bateria.catalogo.gasto', string='Catálogo Insumos/Gastos', required=False)
    
    descripcion_proveedor = fields.Char(string='Modelo / Detalle Específico', required=False)
    info_competencia = fields.Text(string='Info Competencia', compute='_compute_info_competencia')
    
    # 👇 NUEVOS CAMPOS DE FLOTA 👇
    es_para_flota = fields.Boolean(string='¿Para Flota?', default=False)
    vehiculo_id = fields.Many2one('bateria.vehiculo', string='Vehículo Destino')
    servicio_flota_id = fields.Many2one('bateria.vehiculo.servicio', string='Servicio Vinculado', copy=False, readonly=True)
    
    cantidad = fields.Float(string='Cant. Pedida', required=True, default=1.0)
    
    unidad_medida = fields.Selection([
        ('und', 'Unidades (Und)'),
        ('kg', 'Kilogramos (Kg)'),
        ('g', 'Gramos (g)'),
        ('lt', 'Litros (L)'),
        ('m', 'Metros (m)'),
        ('caja', 'Caja / Bulto'),
        ('saco', 'Saco'),
        ('serv', 'Servicio')
    ], string='U.M.', default='und', required=True)
    
    cantidad_recibida = fields.Float(string='Cant. Recibida', default=0.0, readonly=True)
    cantidad_facturada = fields.Float(string='Cant. Facturada', default=0.0, readonly=True)
    
    precio_usd = fields.Float(string='Precio ($)', required=True, default=0.0)
    precio_bs = fields.Float(string='Precio (Bs)', compute='_compute_precios_bs', inverse='_inverse_precios_bs', store=True)
    
    descuento_porcentaje = fields.Float(string='Desc. (%)', default=0.0)
    aplica_iva = fields.Boolean(string='Aplica IVA', default=True)
    
    subtotal_usd = fields.Float(string='Total ($)', compute='_compute_subtotales', store=True)
    subtotal_bs = fields.Float(string='Total (Bs)', compute='_compute_subtotales', store=True)
    subtotal = fields.Float(string='Subtotal Base', compute='_compute_subtotales', store=True)
    
    moneda = fields.Selection(related='compra_id.moneda', store=True)

    @api.depends('producto_maestro_id', 'gasto_id')
    def _compute_info_competencia(self):
        for linea in self:
            historial = []
            seen = set()
            if linea.producto_maestro_id:
                compras_previas = self.env['bateria.compra.linea'].search([
                    ('producto_maestro_id', '=', linea.producto_maestro_id.id),
                    ('compra_id.estado', 'in', ['confirmado', 'recibido', 'facturado', 'pagado'])
                ], order='id desc', limit=6)
                if compras_previas:
                    for c in compras_previas:
                        prov = c.compra_id.proveedor_id.nombre_empresa or 'Desconocido'
                        fecha = c.compra_id.fecha.strftime('%d/%m/%Y') if c.compra_id.fecha else ''
                        detalle = f" ({c.descripcion_proveedor})" if c.descripcion_proveedor and c.descripcion_proveedor != c.producto_maestro_id.nombre else ""
                        info = f"• {prov}{detalle}: ${c.precio_usd:,.2f} ({fecha})"
                        if info not in seen:
                            seen.add(info)
                            historial.append(info)
                    linea.info_competencia = "\n".join(historial)
                else:
                    linea.info_competencia = "No hay historial de compras de este producto."
            elif linea.gasto_id:
                compras_previas = self.env['bateria.compra.linea'].search([
                    ('gasto_id', '=', linea.gasto_id.id),
                    ('compra_id.estado', 'in', ['confirmado', 'recibido', 'facturado', 'pagado'])
                ], order='id desc', limit=6)
                if compras_previas:
                    for c in compras_previas:
                        prov = c.compra_id.proveedor_id.nombre_empresa or 'Desconocido'
                        fecha = c.compra_id.fecha.strftime('%d/%m/%Y') if c.compra_id.fecha else ''
                        detalle = f" ({c.descripcion_proveedor})" if c.descripcion_proveedor and c.descripcion_proveedor != c.gasto_id.name else ""
                        info = f"• {prov}{detalle}: ${c.precio_usd:,.2f} ({fecha})"
                        if info not in seen:
                            seen.add(info)
                            historial.append(info)
                    linea.info_competencia = "\n".join(historial)
                else:
                    linea.info_competencia = "Gasto nuevo (Sin historial previo)."
            else:
                linea.info_competencia = ""

    @api.onchange('producto_maestro_id')
    def _onchange_producto(self):
        if self.producto_maestro_id:
            self.gasto_id = False 
            self.descripcion_proveedor = self.producto_maestro_id.nombre
            self.unidad_medida = 'und'  
            tarifa = self.env['bateria.proveedor.tarifa'].search([
                ('proveedor_id', '=', self.compra_id.proveedor_id.id),
                ('producto_id', '=', self.producto_maestro_id.id)
            ], limit=1)
            self.precio_usd = tarifa.precio if tarifa else self.producto_maestro_id.precio_base_usd

    @api.onchange('gasto_id')
    def _onchange_gasto(self):
        if self.gasto_id:
            self.producto_maestro_id = False
            self.descripcion_proveedor = self.gasto_id.name
            if self.gasto_id.precio_referencia_usd > 0:
                self.precio_usd = self.gasto_id.precio_referencia_usd

    @api.depends('precio_usd', 'compra_id.tasa_aplicada')
    def _compute_precios_bs(self):
        for l in self:
            tasa = l.compra_id.tasa_aplicada if (hasattr(l.compra_id, 'tasa_aplicada') and l.compra_id.tasa_aplicada > 0) else 1.0
            l.precio_bs = l.precio_usd * tasa

    def _inverse_precios_bs(self):
        for l in self:
            tasa = l.compra_id.tasa_aplicada if (hasattr(l.compra_id, 'tasa_aplicada') and l.compra_id.tasa_aplicada > 0) else 1.0
            l.precio_usd = l.precio_bs / tasa if tasa > 0 else 0.0

    @api.onchange('precio_usd')
    def _onchange_sync_bs(self):
        tasa = self.compra_id.tasa_aplicada or 1.0
        self.precio_bs = self.precio_usd * tasa

    @api.onchange('precio_bs')
    def _onchange_sync_usd(self):
        tasa = self.compra_id.tasa_aplicada or 1.0
        if tasa > 0:
            self.precio_usd = self.precio_bs / tasa

    @api.depends('cantidad', 'precio_usd', 'precio_bs', 'compra_id.moneda', 'descuento_porcentaje')
    def _compute_subtotales(self):
        for l in self:
            factor_descuento = 1.0 - (l.descuento_porcentaje / 100.0)
            
            l.subtotal_usd = (l.cantidad * l.precio_usd) * factor_descuento
            l.subtotal_bs = (l.cantidad * l.precio_bs) * factor_descuento
            
            l.subtotal = l.subtotal_usd if l.compra_id.moneda == 'usd' else l.subtotal_bs


class BateriaCompraPago(models.Model):
    _name = 'bateria.compra.pago'
    _description = 'Historial de Pagos de Compras'
    
    compra_id = fields.Many2one('bateria.compra', string='Compra', ondelete='cascade')
    fecha = fields.Date(string='Fecha', default=fields.Date.context_today, required=True)
    caja_id = fields.Many2one('bateria.caja', string='Caja / Banco Origen', required=True)
    metodo_pago = fields.Selection([
        ('efectivo', 'Efectivo'),
        ('pago_movil', 'Pago Móvil'),
        ('zelle', 'Zelle / Transferencia'),
        ('deposito', 'Depósito Bancario')
    ], string='Método', required=True)
    referencia = fields.Char(string='Referencia')
    monto = fields.Float(string='Monto Pagado', required=True)
    moneda = fields.Selection([('usd', 'USD'), ('bs', 'Bs')], string='Moneda', required=True, default='usd')

    @api.onchange('compra_id')
    def _onchange_compra(self):
        if self.compra_id:
            self.moneda = self.compra_id.moneda
            self.monto = self.compra_id.saldo_pendiente

    @api.model_create_multi
    def create(self, vals_list):
        records = super(BateriaCompraPago, self).create(vals_list)
        for res in records:
            compra = res.compra_id
            self.env['bateria.libro.mayor'].create([{
                'fecha': res.fecha, 'caja_id': res.caja_id.id,
                'referencia': res.referencia or f"PAGO-{compra.name}",
                'concepto': f"Pago Compra: {compra.name}", 'tipo_movimiento': 'egreso',
                'monto': res.monto, 'moneda': res.moneda, 'compra_id': compra.id,
            }])
            # 👇 NUEVO: ASIENTO DEL PAGO
            diario = self.env['bateria.diario'].search([('tipo', 'in', ('banco', 'efectivo'))], limit=1)
            if diario:
                cxp = self.env['bateria.cuenta.contable'].search([('name', 'ilike', 'por Pagar')], limit=1)
                banco = res.caja_id.cuenta_contable_id or cxp
                asiento = self.env['bateria.asiento'].create({'fecha': res.fecha, 'referencia': res.referencia or "Pago", 'diario_id': diario.id, 'estado': 'asentado'})
                self.env['bateria.apunte'].create({'asiento_id': asiento.id, 'cuenta_id': cxp.id, 'nombre': "Abono CxP", 'debe': res.monto, 'haber': 0.0})
                self.env['bateria.apunte'].create({'asiento_id': asiento.id, 'cuenta_id': banco.id, 'nombre': "Salida Banco", 'debe': 0.0, 'haber': res.monto})
        return records

class BateriaCatalogoGasto(models.Model):
    _name = 'bateria.catalogo.gasto'
    _description = 'Catálogo Histórico de Gastos'
    _rec_name = 'name'

    name = fields.Char(string='Descripción del Gasto / Consumible', required=True)
    precio_referencia_usd = fields.Float(string='Último Precio de Compra ($)')

class BateriaCompraDiarioWizard(models.TransientModel):
    _name = 'bateria.compra.diario.wizard'
    _description = 'Asistente de Reporte Diario de Compras'

    fecha_inicio = fields.Date(string='Desde', default=fields.Date.context_today, required=True)
    fecha_fin = fields.Date(string='Hasta', default=fields.Date.context_today, required=True)

    def action_generar_reporte(self):
        compras = self.env['bateria.compra'].search([
            ('fecha', '>=', self.fecha_inicio),
            ('fecha', '<=', self.fecha_fin),
            ('estado', 'in', ['confirmado', 'recibido', 'facturado', 'pagado'])
        ], order='fecha asc, id asc')
        
        if not compras:
            raise UserError(f'No hay compras procesadas entre el {self.fecha_inicio.strftime("%d/%m/%Y")} y el {self.fecha_fin.strftime("%d/%m/%Y")}.')
            
        return self.env.ref('bateria_reportes.action_reporte_diario_compras').report_action(compras)

class BateriaCompraLineaExtVentas(models.Model):
    _inherit = 'bateria.compra.linea'

    def _compute_display_name(self):
        for rec in self:
            nombre = rec.descripcion_proveedor
            if not nombre and rec.producto_maestro_id:
                nombre = rec.producto_maestro_id.nombre
            elif not nombre:
                nombre = "Artículo"
                
            precio = getattr(rec, 'precio_usd', 0.0)
            prov = ''
            if hasattr(rec, 'proveedor_id') and rec.proveedor_id:
                prov = rec.proveedor_id.display_name or ''
            
            rec.display_name = f"{nombre} | Costo: ${precio} | Prov: {prov}"