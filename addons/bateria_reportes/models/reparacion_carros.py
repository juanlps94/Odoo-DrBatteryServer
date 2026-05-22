from odoo import models, fields, api
from odoo.exceptions import UserError

class BateriaReparacionCarro(models.Model):
    _name = 'bateria.reparacion.carro'
    _description = 'Orden de Reparación de Vehículos (JJS)'
    _order = 'fecha_entrada desc, id desc'

    name = fields.Char(string='N° de Identificación / Control', required=True, default='Nuevo', copy=False)
    fecha_entrada = fields.Date(string='Fecha de Entrada', default=fields.Date.context_today, required=True)
    cliente_id = fields.Many2one('bateria.cliente', string='Cliente', required=True)
    
    foto_vehiculo = fields.Binary(string='Foto del Vehículo al Entrar', required=True)
    
    marca = fields.Char(string='Marca')
    modelo = fields.Char(string='Modelo')
    anio = fields.Char(string='Año')
    placa = fields.Char(string='Placas')
    vin = fields.Char(string='Serial de Carrocería (VIN)')
    kilometraje = fields.Char(string='Kilometraje')
    
    observaciones = fields.Text(string='Reporte de Inspección', help="Ej: Posee reproductor, cauchos buenos...")
    trabajo_realizar = fields.Text(string='Trabajo a Realizar')
    mecanico = fields.Char(string='Mecánico Asignado')

    moneda = fields.Selection([('usd', 'USD ($)'), ('bs', 'Bolívares (Bs)')], required=True, default='usd', string="Moneda a Mostrar al Cliente")
    moneda_referencia = fields.Selection([
        ('usdt', 'USDT (Binance/Paralelo)'), 
        ('usd', 'Dólar BCV'), 
        ('eur', 'Euro BCV')
    ], string='Tasa Referencia', default='usd', required=True)
    usar_tasa_personalizada = fields.Boolean(string='Usar Tasa Personalizada')
    tasa_cambio = fields.Float(string='Tasa Cambio')
    tasa_aplicada = fields.Float(string='Tasa del Día', compute='_compute_tasa_aplicada', store=True)

    ubicacion_vehiculo = fields.Selection([
        ('galpon', 'En Galpón (Interno)'), 
        ('externo', 'Externo (Fuera del taller)')
    ], string='Ubicación del Vehículo', default='galpon')
    
    fecha_estimada_entrega = fields.Datetime(string='Tiempo Estimado de Entrega')
    
    # 👇 NUEVO: MOTOR DE TIEMPO PARA ALERTAS ROJAS 👇
    es_atrasado = fields.Boolean(string='Tiempo Excedido', compute='_compute_es_atrasado')

    @api.depends('fecha_estimada_entrega', 'estado')
    def _compute_es_atrasado(self):
        ahora = fields.Datetime.now()
        for r in self:
            if r.fecha_estimada_entrega and r.estado not in ('listo', 'reparto') and r.fecha_estimada_entrega < ahora:
                r.es_atrasado = True
            else:
                r.es_atrasado = False

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
        self._compute_tasa_aplicada()

    pieza_ids = fields.One2many('bateria.reparacion.carro.pieza', 'reparacion_carro_id', string='Repuestos y Servicios')
    
    total_repuestos = fields.Float(string='Total en Repuestos', compute='_compute_totales', store=True)
    costo_repuestos = fields.Float(string='Costo Repuestos', compute='_compute_totales', store=True)
    ganancia_repuestos = fields.Float(string='Ganancia Repuestos', compute='_compute_totales', store=True)
    
    total_mano_obra = fields.Float(string='Total Mano de Obra', compute='_compute_totales', store=True)
    mo_taller = fields.Float(string='Mano de Obra Taller (50%)', compute='_compute_totales', store=True)
    mo_mecanico = fields.Float(string='Mano de Obra Mecánico (50%)', compute='_compute_totales', store=True)

    total_venta = fields.Float(string='Total Cliente ($)', compute='_compute_totales', store=True)
    total_costo_compra = fields.Float(string='Total Costos ($)', compute='_compute_totales', store=True)
    
    ganancia_neta_taller = fields.Float(string='Ganancia Neta Taller', compute='_compute_totales', store=True)
    ganancia_bruta = fields.Float(string='Ganancia Bruta', compute='_compute_totales', store=True) 
    
    gasto_adm = fields.Float(string='Gasto Adm (10%) ($)', compute='_compute_totales', store=True)
    total_reparticion = fields.Float(string='Repartición Socios', compute='_compute_totales', store=True)
    
    ganancia_johan = fields.Float(string='Johan (50%)', compute='_compute_totales', store=True)
    ganancia_leo = fields.Float(string='Leo (50%)', compute='_compute_totales', store=True)
    
    total_ganancia = fields.Float(string='Ganancia Final Libre', compute='_compute_totales', store=True)

    pago_ids = fields.One2many('bateria.reparacion.pago', 'reparacion_id', string='Historial de Pagos')
    monto_pagado = fields.Float(string='Total Abonado', compute='_compute_pagos', store=True)
    saldo_pendiente = fields.Float(string='Saldo Pendiente', compute='_compute_pagos', store=True)

    compra_id = fields.Many2one('bateria.compra', string='Orden de Compra Generada', readonly=True)
    compra_existente_id = fields.Many2one('bateria.compra', string='Buscar Compra Previa', domain="[('estado', '!=', 'cancelado')]")

    # 👇 NUEVO: FASE DE REPARTIR GANANCIAS AÑADIDA 👇
    estado = fields.Selection([
        ('recepcion', '1. Recepción'),
        ('inspeccion', '2. Inspección'),
        ('presupuesto', '3. Presupuesto'),
        ('cobro', '4. Cobro de Inicial'),
        ('compras', '5. Compra de Repuestos'),
        ('reparacion', '6. En Reparación'),
        ('listo', '7. Entregado'),
        ('reparto', '8. Ganancias Repartidas')
    ], default='recepcion', string='Estado')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                if vals.get('ubicacion_vehiculo') == 'externo':
                    vals['name'] = self.env['ir.sequence'].next_by_code('bateria.carro.externo.seq') or 'EXT-0000'
                else:
                    vals['name'] = self.env['ir.sequence'].next_by_code('bateria.reparacion.carro.seq') or 'TALLER-0000'
        return super(BateriaReparacionCarro, self).create(vals_list)

    @api.depends('pieza_ids.precio_venta', 'pieza_ids.precio_compra', 'pieza_ids.cantidad', 'pieza_ids.tipo_linea')
    def _compute_totales(self):
        for r in self:
            rep_venta = sum(p.precio_venta * p.cantidad for p in r.pieza_ids if p.tipo_linea == 'repuesto')
            rep_costo = sum(p.precio_compra * p.cantidad for p in r.pieza_ids if p.tipo_linea == 'repuesto')
            r.total_repuestos = rep_venta
            r.costo_repuestos = rep_costo
            r.ganancia_repuestos = rep_venta - rep_costo
            
            mo_tot = sum(p.precio_venta * p.cantidad for p in r.pieza_ids if p.tipo_linea == 'servicio')
            mo_cost = sum(p.precio_compra * p.cantidad for p in r.pieza_ids if p.tipo_linea == 'servicio')
            r.total_mano_obra = mo_tot
            r.mo_mecanico = mo_cost
            r.mo_taller = mo_tot - mo_cost
            
            r.total_venta = rep_venta + mo_tot
            r.total_costo_compra = rep_costo + mo_cost
            
            g_neta_tal = r.mo_taller + r.ganancia_repuestos
            r.ganancia_neta_taller = g_neta_tal
            r.ganancia_bruta = g_neta_tal 
            
            g_adm = g_neta_tal * 0.10 if g_neta_tal > 0 else 0.0
            r.gasto_adm = g_adm
            
            reparticion = g_neta_tal - g_adm
            r.total_reparticion = reparticion
            
            r.ganancia_johan = reparticion * 0.50
            r.ganancia_leo = reparticion * 0.50
            r.total_ganancia = reparticion

    @api.depends('pago_ids.monto', 'pago_ids.moneda', 'total_venta', 'moneda', 'tasa_aplicada')
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
            r.saldo_pendiente = r.total_venta - pagado_convertido

    def action_fase_inspeccion(self):
        for r in self: r.estado = 'inspeccion'

    def action_iniciar_presupuesto(self):
        for r in self: r.estado = 'presupuesto'
        
    def action_fase_cobro(self):
        for r in self:
            if not r.fecha_estimada_entrega:
                raise UserError("Debes definir el 'Tiempo Estimado de Entrega' al cliente antes de pasar a cobrar.")
            r.estado = 'cobro'

    def action_importar_compra(self):
        for r in self:
            if not r.compra_existente_id:
                raise UserError("Por favor, busca y selecciona una factura de compra de la lista para importarla.")
            r.compra_id = r.compra_existente_id.id
            nuevas_lineas = []
            for linea in r.compra_existente_id.linea_ids:
                ya_existe = r.pieza_ids.filtered(lambda p: p.compra_linea_id.id == linea.id)
                if not ya_existe:
                    desc = linea.descripcion_proveedor or (linea.producto_maestro_id.nombre if linea.producto_maestro_id else (linea.gasto_id.name if linea.gasto_id else 'Repuesto Importado'))
                    nuevas_lineas.append((0, 0, {
                        'tipo_linea': 'repuesto',
                        'name': desc,
                        'cantidad': linea.cantidad,
                        'precio_compra': linea.precio_usd,
                        'precio_venta': linea.precio_usd,
                        'compra_linea_id': linea.id
                    }))
            if nuevas_lineas:
                r.write({'pieza_ids': nuevas_lineas})
            if r.estado in ('recepcion', 'inspeccion'):
                r.estado = 'presupuesto'
            r.compra_existente_id = False 
            return {
                'effect': {'fadeout': 'slow', 'message': '¡Repuestos importados exitosamente desde Compras!', 'type': 'rainbow_man'}
            }

    def action_enviar_a_compras(self):
        for r in self:
            if r.total_venta > 0 and r.monto_pagado < (r.total_venta * 0.40):
                raise UserError("🛑 ¡ALTO! El cliente debe abonar al menos el 40% de inicial del presupuesto para poder procesar la compra de repuestos o arreglar el carro.")
            piezas_nuevas = r.pieza_ids.filtered(lambda p: not p.compra_linea_id and p.tipo_linea == 'repuesto')
            if not piezas_nuevas:
                raise UserError("No hay repuestos nuevos para enviar. (Recuerda que la Mano de Obra se paga internamente y no se envía al módulo de Compras).")
            if r.compra_id:
                if r.compra_id.estado in ('facturado', 'pagado', 'cancelado'):
                    raise UserError(f"La Orden de Compra {r.compra_id.name} ya está Cerrada. No le puedes inyectar más repuestos.")
                for pieza in piezas_nuevas:
                    nueva_linea = self.env['bateria.compra.linea'].create({
                        'compra_id': r.compra_id.id,
                        'descripcion_proveedor': pieza.name,
                        'cantidad': pieza.cantidad,
                        'precio_usd': pieza.precio_compra,
                        'aplica_iva': True,
                    })
                    pieza.compra_linea_id = nueva_linea.id
                mensaje = f"¡Se agregaron {len(piezas_nuevas)} repuestos nuevos a la compra existente ({r.compra_id.name})!"
            else:
                cc = self.env['bateria.centro.costo'].search([], limit=1)
                ubic = self.env['bateria.ubicacion'].search([], limit=1)
                prov = self.env['bateria.proveedor'].search([('nombre_empresa', '=', 'PROVEEDORES VARIOS TALLER')], limit=1)
                if not prov:
                    prov = self.env['bateria.proveedor'].create({'nombre_empresa': 'PROVEEDORES VARIOS TALLER', 'rif': 'J-000000000'})
                nueva_compra = self.env['bateria.compra'].create({
                    'name': f'Repuestos Taller - {r.name} ({r.placa})',
                    'empresa_compra': 'jjs_2021',
                    'proveedor_id': prov.id,
                    'centro_costo_id': cc.id if cc else False,
                    'ubicacion_id': ubic.id if ubic else False,
                    'estado': 'borrador'
                })
                for pieza in piezas_nuevas:
                    nueva_linea = self.env['bateria.compra.linea'].create({
                        'compra_id': nueva_compra.id,
                        'descripcion_proveedor': pieza.name,
                        'cantidad': pieza.cantidad,
                        'precio_usd': pieza.precio_compra,
                        'aplica_iva': True,
                    })
                    pieza.compra_linea_id = nueva_linea.id
                r.compra_id = nueva_compra.id
                mensaje = "¡Presupuesto enviado al Gerente de Pagos con éxito!"
            r.estado = 'compras'
            return {'effect': {'fadeout': 'slow', 'message': mensaje, 'type': 'rainbow_man'}}

    def action_sincronizar_costos(self):
        for r in self:
            if not r.compra_id:
                raise UserError("No hay una Orden de Compra vinculada.")
            lineas_compra = r.compra_id.linea_ids
            for pieza in r.pieza_ids.filtered(lambda p: p.tipo_linea == 'repuesto'):
                if pieza.compra_linea_id and pieza.compra_linea_id in lineas_compra:
                    pieza.precio_compra = pieza.compra_linea_id.precio_usd
                else:
                    match = lineas_compra.filtered(lambda l: l.descripcion_proveedor and pieza.name.lower() in l.descripcion_proveedor.lower())
                    if match:
                        pieza.precio_compra = match[0].precio_usd

    def action_iniciar_reparacion(self):
        for r in self:
            if r.total_venta > 0 and r.monto_pagado < (r.total_venta * 0.40):
                raise UserError("🛑 ¡ALTO! El cliente debe pagar al menos el 40% de inicial del presupuesto para poder arreglar el carro.")
            r.estado = 'reparacion'

    def action_marcar_listo(self):
        for r in self: r.estado = 'listo'
        
    def action_volver_paso_anterior(self):
        for r in self:
            if r.estado == 'inspeccion':
                r.estado = 'recepcion'
            elif r.estado == 'presupuesto':
                r.estado = 'inspeccion'
            elif r.estado == 'cobro':
                r.estado = 'presupuesto'
            elif r.estado == 'compras':
                r.estado = 'cobro'
            elif r.estado == 'reparacion':
                r.estado = 'compras'
            elif r.estado == 'listo':
                r.estado = 'reparacion'

    # 👇 NUEVO: FUNCIÓN PARA REPARTIR GANANCIAS 👇
    def action_fase_reparto(self):
        for r in self:
            r.estado = 'reparto'

class BateriaReparacionCarroPieza(models.Model):
    _name = 'bateria.reparacion.carro.pieza'
    _description = 'Repuestos de la Reparación de Vehículo'

    reparacion_carro_id = fields.Many2one('bateria.reparacion.carro', ondelete='cascade')
    compra_linea_id = fields.Many2one('bateria.compra.linea', string='Línea de Compra Vinculada', ondelete='set null')
    
    tipo_linea = fields.Selection([
        ('repuesto', '📦 Repuesto / Material'),
        ('servicio', '🔧 Servicio / Mano de Obra')
    ], string='Tipo', default='repuesto', required=True)
    
    name = fields.Char(string='Descripción del Trabajo / Repuesto', required=True)
    cantidad = fields.Float(string='Cant.', default=1.0)
    
    precio_venta = fields.Float(string='Precio Cliente ($)', help="Lo que se le cobra al cliente", required=True)
    precio_compra = fields.Float(string='Costo / Pago Mecánico ($)', help="Lo que costó el repuesto o lo que se le paga al mecánico")
    
    ganancia = fields.Float(string='Ganancia Bruta ($)', compute='_compute_ganancia', store=True)
    
    @api.depends('precio_compra', 'precio_venta', 'cantidad')
    def _compute_ganancia(self):
        for r in self:
            r.ganancia = (r.precio_venta - r.precio_compra) * r.cantidad

    @api.onchange('precio_venta', 'tipo_linea')
    def _onchange_precio_venta_servicio(self):
        if self.tipo_linea == 'servicio' and self.precio_venta > 0:
            self.precio_compra = self.precio_venta * 0.50

class BateriaReparacionPago(models.Model):
    _name = 'bateria.reparacion.pago'
    _description = 'Historial de Pagos de Reparaciones'
    
    reparacion_id = fields.Many2one('bateria.reparacion.carro', string='Orden de Reparación', ondelete='cascade')
    fecha = fields.Date(string='Fecha', default=fields.Date.context_today, required=True)
    caja_id = fields.Many2one('bateria.caja', string='Caja / Banco Destino', required=True)
    metodo_pago = fields.Selection([
        ('efectivo', 'Efectivo'),
        ('pago_movil', 'Pago Móvil'),
        ('zelle', 'Zelle / Transferencia'),
        ('deposito', 'Depósito Bancario'),
        ('punto', 'Punto de Venta')
    ], string='Método', required=True)
    referencia = fields.Char(string='Referencia / Serial Billetes')
    monto = fields.Float(string='Monto Pagado', required=True)
    moneda = fields.Selection([('usd', 'USD'), ('bs', 'Bs')], string='Moneda', required=True, default='usd')

    @api.onchange('reparacion_id')
    def _onchange_reparacion(self):
        if self.reparacion_id:
            self.moneda = self.reparacion_id.moneda
            self.monto = self.reparacion_id.saldo_pendiente

    @api.model_create_multi
    def create(self, vals_list):
        records = super(BateriaReparacionPago, self).create(vals_list)
        for res in records:
            if res.metodo_pago == 'efectivo':
                continue
            rep = res.reparacion_id
            concepto_txt = f"Cobro de Taller: {rep.name} - {rep.placa}"
            if rep and rep.cliente_id:
                concepto_txt += f" | Cliente: {rep.cliente_id.name}"
                
            self.env['bateria.libro.mayor'].create([{
                'fecha': res.fecha,
                'caja_id': res.caja_id.id,
                'referencia': res.referencia or f"PAGO-REP-{rep.name}",
                'concepto': concepto_txt,
                'tipo_movimiento': 'ingreso',
                'monto': res.monto,
                'moneda': res.moneda,
            }])
        return records

class BateriaReporteTallerWizard(models.TransientModel):
    _name = 'bateria.reporte.taller.wizard'
    _description = 'Wizard para Reporte de Cierre Semanal'

    fecha_inicio = fields.Date(string='Fecha Inicio', required=True, default=fields.Date.context_today)
    fecha_fin = fields.Date(string='Fecha Fin', required=True, default=fields.Date.context_today)

    def action_imprimir_reporte(self):
        ordenes = self.env['bateria.reparacion.carro'].search([
            ('fecha_entrada', '>=', self.fecha_inicio),
            ('fecha_entrada', '<=', self.fecha_fin),
            ('estado', 'in', ['reparacion', 'listo', 'reparto']) 
        ], order='fecha_entrada asc')

        if not ordenes:
            raise UserError("No se encontraron vehículos procesados en este rango de fechas.")

        return self.env.ref('bateria_reportes.action_report_cierre_semanal_taller').with_context(
            fecha_inicio=self.fecha_inicio,
            fecha_fin=self.fecha_fin
        ).report_action(ordenes)