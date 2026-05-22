from odoo import models, fields, api

class BateriaCatalogoServicio(models.Model):
    _name = 'bateria.catalogo.servicio'
    _description = 'Directorio de Servicios Fijos'
    name = fields.Char(string='Nombre del Servicio', required=True)

class BateriaPagoServicio(models.Model):
    _name = 'bateria.pago.servicio'
    _description = 'Pago de Servicios'
    _order = 'fecha desc, id desc'

    servicio_id = fields.Many2one('bateria.catalogo.servicio', string='Servicio a Pagar', required=True)
    name = fields.Char(string='Descripción / Mes', required=True)
    fecha = fields.Date(string='Fecha', default=fields.Date.context_today, required=True)

    tipo_documento = fields.Selection([
        ('nota_entrega', 'Recibo Administrativo'),
        ('factura', 'Factura Fiscal')
    ], string='Tipo de Documento', required=True, default='nota_entrega')
    
    
    # 👇 NUEVO: Cuenta Contable y Asiento
    cuenta_id = fields.Many2one('bateria.cuenta.contable', string='Cuenta Contable', required=True)
    asiento_id = fields.Many2one('bateria.asiento', string='Asiento Generado', readonly=True)

    empresa_paga = fields.Selection([
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
    ], string='Empresa/Personal', required=True, default='don_juan')
    
    cuenta = fields.Char(string='Número de Contrato / Ref')
    moneda = fields.Selection([('usd', 'USD'), ('bs', 'Bs')], string='Moneda del Servicio', required=True, default='bs')
    
    monto_base = fields.Float(string='Monto Base (Subtotal)', required=True, default=0.0)
    aplica_iva = fields.Boolean(string='Aplica IVA (16%)', default=False)
    monto_iva = fields.Float(string='IVA (16%)', compute='_compute_totales_iva', store=True)
    monto_total = fields.Float(string='Monto Total (Deuda)', compute='_compute_totales_iva', store=True)

    @api.depends('monto_base', 'aplica_iva')
    def _compute_totales_iva(self):
        for r in self:
            r.monto_iva = r.monto_base * 0.16 if r.aplica_iva else 0.0
            r.monto_total = r.monto_base + r.monto_iva

    def action_agregar_iva(self):
        for r in self: r.aplica_iva = True

    def action_quitar_iva(self):
        for r in self: r.aplica_iva = False
    
    moneda_referencia = fields.Selection([('usd', 'Dólar BCV'), ('eur', 'Euro BCV')], string='Tasa Referencia', default='usd', required=True)
    usar_tasa_personalizada = fields.Boolean(string='Usar Tasa Personalizada')
    tasa_cambio = fields.Float(string='Tasa Cambio')
    tasa_aplicada = fields.Float(string='Tasa del Día', compute='_compute_tasa_aplicada', store=True)

    pago_ids = fields.One2many('bateria.servicio.pago', 'servicio_pago_id', string='Historial de Pagos')
    monto_pagado = fields.Float(string='Total Pagado', compute='_compute_pagos', store=True)
    saldo_pendiente = fields.Float(string='Saldo Pendiente', compute='_compute_pagos', store=True)

    estado = fields.Selection([('borrador', 'Borrador'), ('confirmado', 'Por Pagar'), ('pagado', 'Pagado')], default='borrador', string='Estado')

    # 👇 NUEVO: Crear el Asiento Contable
    def action_confirmar_servicio(self):
        for r in self:
            if r.monto_total <= 0: raise UserError("El monto debe ser mayor a cero.")
            diario = self.env['bateria.diario'].search([('tipo', '=', 'compra')], limit=1)
            cxp = self.env['bateria.cuenta.contable'].search([('name', 'ilike', 'por Pagar')], limit=1) or r.cuenta_id
            iva = self.env['bateria.cuenta.contable'].search([('name', 'ilike', 'IVA')], limit=1) or r.cuenta_id
            
            asiento = self.env['bateria.asiento'].create({
                'fecha': r.fecha, 'referencia': f"Servicio: {r.servicio_id.name}",
                'diario_id': diario.id, 'estado': 'asentado'
            })
            self.env['bateria.apunte'].create({'asiento_id': asiento.id, 'cuenta_id': r.cuenta_id.id, 'nombre': r.name, 'debe': r.monto_base, 'haber': 0.0})
            if r.aplica_iva and r.monto_iva > 0:
                self.env['bateria.apunte'].create({'asiento_id': asiento.id, 'cuenta_id': iva.id, 'nombre': "IVA Crédito", 'debe': r.monto_iva, 'haber': 0.0})
            self.env['bateria.apunte'].create({'asiento_id': asiento.id, 'cuenta_id': cxp.id, 'nombre': "CxP", 'debe': 0.0, 'haber': r.monto_total})
            
            r.asiento_id = asiento.id
            r.estado = 'confirmado'

    @api.depends('moneda_referencia', 'usar_tasa_personalizada', 'tasa_cambio')
    def _compute_tasa_aplicada(self):
        for r in self:
            if r.usar_tasa_personalizada and r.tasa_cambio > 0: r.tasa_aplicada = r.tasa_cambio
            else:
                param = 'bateria.tasa_bcv_usd' if r.moneda_referencia == 'usd' else 'bateria.tasa_bcv_eur'
                r.tasa_aplicada = float(self.env['ir.config_parameter'].sudo().get_param(param, default='1.0'))

    def action_actualizar_tasa_bcv_manual(self):
        try: self.env['bateria.bcv.scraper'].actualizar_tasas_completas()
        except: pass
        self._compute_tasa_aplicada()

    @api.depends('pago_ids.monto', 'pago_ids.moneda', 'monto_total', 'moneda', 'tasa_aplicada')
    def _compute_pagos(self):
        for r in self:
            pagado_convertido = sum(p.monto if p.moneda == r.moneda else (p.monto / (r.tasa_aplicada or 1.0) if r.moneda == 'usd' else p.monto * (r.tasa_aplicada or 1.0)) for p in r.pago_ids)
            r.monto_pagado = pagado_convertido
            r.saldo_pendiente = r.monto_total - pagado_convertido
            if r.estado in ('confirmado', 'pagado'):
                r.estado = 'pagado' if r.saldo_pendiente <= 0 and r.monto_total > 0 else 'confirmado'

class BateriaServicioPago(models.Model):
    _name = 'bateria.servicio.pago'
    _description = 'Historial de Pagos de Servicios'
    
    servicio_pago_id = fields.Many2one('bateria.pago.servicio', string='Servicio', ondelete='cascade')
    fecha = fields.Date(string='Fecha', default=fields.Date.context_today, required=True)
    caja_id = fields.Many2one('bateria.caja', string='Caja / Banco Origen', required=True)
    metodo_pago = fields.Selection([('efectivo', 'Efectivo'), ('pago_movil', 'Pago Móvil'), ('zelle', 'Zelle / Transf.'), ('deposito', 'Depósito')], string='Método', required=True)
    referencia = fields.Char(string='Referencia')
    monto = fields.Float(string='Monto Pagado', required=True)
    moneda = fields.Selection([('usd', 'USD'), ('bs', 'Bs')], string='Moneda', required=True, default='bs')

    @api.onchange('servicio_pago_id')
    def _onchange_servicio(self):
        if self.servicio_pago_id:
            self.moneda, self.monto = self.servicio_pago_id.moneda, self.servicio_pago_id.saldo_pendiente

    @api.model_create_multi
    def create(self, vals_list):
        records = super(BateriaServicioPago, self).create(vals_list)
        for res in records:
            srv = res.servicio_pago_id
            self.env['bateria.libro.mayor'].create([{
                'fecha': res.fecha, 'caja_id': res.caja_id.id,
                'referencia': res.referencia or "PAGO-SRV", 'concepto': f"Pago: {srv.servicio_id.name}",
                'tipo_movimiento': 'egreso', 'monto': res.monto, 'moneda': res.moneda,
            }])
            # 👇 Asiento del Pago
            diario = self.env['bateria.diario'].search([('tipo', 'in', ('banco', 'efectivo'))], limit=1)
            if diario:
                cxp = self.env['bateria.cuenta.contable'].search([('name', 'ilike', 'por Pagar')], limit=1) or srv.cuenta_id
                banco = res.caja_id.cuenta_contable_id or cxp
                asiento = self.env['bateria.asiento'].create({'fecha': res.fecha, 'referencia': res.referencia or "Pago", 'diario_id': diario.id, 'estado': 'asentado'})
                self.env['bateria.apunte'].create({'asiento_id': asiento.id, 'cuenta_id': cxp.id, 'nombre': "Abono CxP", 'debe': res.monto, 'haber': 0.0})
                self.env['bateria.apunte'].create({'asiento_id': asiento.id, 'cuenta_id': banco.id, 'nombre': "Salida Banco", 'debe': 0.0, 'haber': res.monto})
        return records
    
# =================================================================================
# WIZARD DE REPORTE DE SERVICIOS
# =================================================================================
class BateriaServicioReporteWizard(models.TransientModel):
    _name = 'bateria.servicio.reporte.wizard'
    _description = 'Asistente para Reporte de Servicios'

    fecha_inicio = fields.Date(string='Fecha de Inicio', required=True)
    fecha_fin = fields.Date(string='Fecha de Fin', required=True, default=fields.Date.context_today)

    def action_generar_reporte(self):
        from odoo.exceptions import UserError
        domain = [('fecha', '>=', self.fecha_inicio), ('fecha', '<=', self.fecha_fin)]
        servicios = self.env['bateria.pago.servicio'].search(domain, order='fecha asc')
        if not servicios:
            raise UserError("No se encontraron servicios pagados en este rango de fechas.")
        return self.env.ref('bateria_reportes.action_reporte_diario_servicios').report_action(servicios)