from odoo import models, fields, api
from odoo.exceptions import UserError

class BateriaGastoOperativo(models.Model):
    _name = 'bateria.gasto.operativo'
    _description = 'Registro de Gastos Operativos'
    _order = 'fecha desc, id desc'

    # 👇 EL CAMPO NATIVO MULTICOMPAÑÍA QUE REEMPLAZA A EMPRESA_PAGA 👇
    company_id = fields.Many2one('res.company', string='Compañía', required=True, default=lambda self: self.env.company)

    tipo_documento = fields.Selection([
        ('nota_entrega', 'Recibo Administrativo'),
        ('factura', 'Factura Fiscal')
    ], string='Tipo de Documento', required=True, default='nota_entrega')
    

    fecha = fields.Date(string='Fecha', default=fields.Date.context_today, required=True)
    name = fields.Char(string='Descripción Gasto', required=True)
    proveedor_id = fields.Many2one('bateria.proveedor', string='Proveedor Servicio')
    cuenta_id = fields.Many2one('bateria.cuenta.contable', string='Cuenta Contable de Gasto')
    asiento_id = fields.Many2one('bateria.asiento', string='Asiento Contable Generado', readonly=True)
    cuenta = fields.Char(string='Cuenta / Referencia')
    moneda = fields.Selection([('usd', 'USD'), ('bs', 'Bs')], string='Moneda del Gasto', required=True, default='bs')
    
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
    
    moneda_referencia = fields.Selection([('usdt', 'USDT'), ('usd', 'Dólar BCV'), ('eur', 'Euro BCV')], default='usd', required=True)
    usar_tasa_personalizada = fields.Boolean(string='Usar Tasa Personalizada')
    tasa_cambio = fields.Float(string='Tasa Cambio')
    tasa_aplicada = fields.Float(string='Tasa del Día', compute='_compute_tasa_aplicada', store=True)

    pago_ids = fields.One2many('bateria.gasto.pago', 'gasto_id', string='Historial de Pagos')
    monto_pagado = fields.Float(string='Total Pagado', compute='_compute_pagos', store=True)
    saldo_pendiente = fields.Float(string='Saldo Pendiente', compute='_compute_pagos', store=True)

    estado = fields.Selection([('borrador', 'Borrador'), ('confirmado', 'Por Pagar'), ('pagado', 'Pagado')], default='borrador')

    def action_confirmar_gasto(self):
        for r in self:
            if r.monto_total <= 0:
                raise UserError("El monto del gasto debe ser mayor a cero.")

            # 1. FRENO CONTABLE: Solo hace esto si es Factura
            if r.tipo_documento == 'factura':  
                diario = self.env['bateria.diario'].search([('tipo', '=', 'compra'), ('company_id', '=', r.company_id.id)], limit=1)
                
                cuenta_cxp = self.env['bateria.cuenta.contable'].search([
                    ('name', 'ilike', 'por Pagar'), '|', ('company_id', '=', False), ('company_id', '=', r.company_id.id)
                ], limit=1) or r.cuenta_id
                
                cuenta_iva = self.env['bateria.cuenta.contable'].search([
                    ('name', 'ilike', 'IVA'), '|', ('company_id', '=', False), ('company_id', '=', r.company_id.id)
                ], limit=1) or r.cuenta_id

                asiento = self.env['bateria.asiento'].create({'fecha': r.fecha, 'referencia': f"Gasto: {r.name}", 'diario_id': diario.id, 'estado': 'asentado', 'company_id': r.company_id.id})
                self.env['bateria.apunte'].create({'asiento_id': asiento.id, 'cuenta_id': r.cuenta_id.id, 'nombre': f"Gasto Operativo: {r.name}", 'debe': r.monto_base, 'haber': 0.0})
                
                if r.aplica_iva and r.monto_iva > 0:
                    self.env['bateria.apunte'].create({'asiento_id': asiento.id, 'cuenta_id': cuenta_iva.id, 'nombre': f"IVA Crédito: {r.name}", 'debe': r.monto_iva, 'haber': 0.0})
                    
                self.env['bateria.apunte'].create({'asiento_id': asiento.id, 'cuenta_id': cuenta_cxp.id, 'nombre': f"Cuentas por Pagar: {r.name}", 'debe': 0.0, 'haber': r.monto_total})
                
                r.asiento_id = asiento.id
            
            # 2. CAMBIO DE ESTADO: Esto ahora está fuera del "if", así que aplica para Notas y Facturas
            r.estado = 'confirmado'

    @api.depends('moneda_referencia', 'usar_tasa_personalizada', 'tasa_cambio')
    def _compute_tasa_aplicada(self):
        for r in self:
            if r.usar_tasa_personalizada and r.tasa_cambio > 0: r.tasa_aplicada = r.tasa_cambio
            else:
                param = 'bateria.tasa_usdt' if r.moneda_referencia == 'usdt' else ('bateria.tasa_bcv_usd' if r.moneda_referencia == 'usd' else 'bateria.tasa_bcv_eur')
                r.tasa_aplicada = float(self.env['ir.config_parameter'].sudo().get_param(param, default='1.0'))

    def action_actualizar_tasa_bcv_manual(self):
        try:
            self.env['bateria.bcv.scraper'].actualizar_tasas_completas()
        except: 
            pass
        self._compute_tasa_aplicada()

    @api.depends('pago_ids.monto', 'pago_ids.moneda', 'monto_total', 'moneda', 'tasa_aplicada')
    def _compute_pagos(self):
        for r in self:
            pagado_convertido = 0.0
            for p in r.pago_ids:
                if p.moneda == r.moneda: pagado_convertido += p.monto
                else:
                    tasa = r.tasa_aplicada if r.tasa_aplicada > 0 else 1.0
                    pagado_convertido += (p.monto / tasa) if (r.moneda == 'usd' and p.moneda == 'bs') else (p.monto * tasa)

            r.monto_pagado = pagado_convertido
            r.saldo_pendiente = r.monto_total - pagado_convertido
            if r.estado in ('confirmado', 'pagado'): r.estado = 'pagado' if (r.saldo_pendiente <= 0 and r.monto_total > 0) else 'confirmado'

class BateriaGastoPago(models.Model):
    _name = 'bateria.gasto.pago'
    _description = 'Historial de Pagos de Gastos'
    
    gasto_id = fields.Many2one('bateria.gasto.operativo', string='Gasto', ondelete='cascade')
    fecha = fields.Date(string='Fecha', default=fields.Date.context_today, required=True)
    caja_id = fields.Many2one('bateria.caja', string='Caja / Banco Origen', required=True)
    metodo_pago = fields.Selection([('efectivo', 'Efectivo'), ('pago_movil', 'Pago Móvil'), ('zelle', 'Zelle / Transferencia'), ('deposito', 'Depósito Bancario')], required=True)
    referencia = fields.Char(string='Referencia')
    monto = fields.Float(string='Monto Pagado', required=True)
    moneda = fields.Selection([('usd', 'USD'), ('bs', 'Bs')], string='Moneda', required=True, default='bs')

    @api.model_create_multi
    def create(self, vals_list):
        records = super(BateriaGastoPago, self).create(vals_list)
        for res in records:
            gasto = res.gasto_id
            
            # 1. EL PAGO VA AL LIBRO MAYOR SIEMPRE (Para cuadrar caja), CON SU ETIQUETA CORRESPONDIENTE
            self.env['bateria.libro.mayor'].create([{
                'company_id': gasto.company_id.id, 
                'fecha': res.fecha, 
                'caja_id': res.caja_id.id, 
                'referencia': res.referencia, 
                'concepto': f"Pago: {gasto.name}", 
                'tipo_movimiento': 'egreso', 
                'monto': res.monto, 
                'moneda': res.moneda,
                'tipo_documento': gasto.tipo_documento # 👈 Hereda si es Nota de Entrega o Factura
            }])
            
            # 2. FRENO CONTABLE: EL ASIENTO EN EL LIBRO DIARIO SOLO SE CREA SI ES FACTURA
            if gasto.tipo_documento == 'factura':
                diario_banco = self.env['bateria.diario'].search([('tipo', 'in', ('banco', 'efectivo')), ('company_id', '=', gasto.company_id.id)], limit=1)
                
                if diario_banco:
                    cuenta_cxp = self.env['bateria.cuenta.contable'].search([('name', 'ilike', 'por Pagar'), '|', ('company_id', '=', False), ('company_id', '=', gasto.company_id.id)], limit=1) or gasto.cuenta_id
                    cuenta_banco = res.caja_id.cuenta_contable_id or cuenta_cxp
                    
                    asiento_pago = self.env['bateria.asiento'].create({
                        'company_id': gasto.company_id.id, 
                        'fecha': res.fecha, 
                        'referencia': res.referencia, 
                        'diario_id': diario_banco.id, 
                        'estado': 'asentado'
                    })
                    
                    self.env['bateria.apunte'].create({
                        'asiento_id': asiento_pago.id, 
                        'cuenta_id': cuenta_cxp.id, 
                        'nombre': f"Abono a CxP: {gasto.name}", 
                        'debe': res.monto, 
                        'haber': 0.0
                    })
                    
                    self.env['bateria.apunte'].create({
                        'asiento_id': asiento_pago.id, 
                        'cuenta_id': cuenta_banco.id, 
                        'nombre': f"Salida: {gasto.name}", 
                        'debe': 0.0, 
                        'haber': res.monto
                    })
                    
        return records

class BateriaGastoReporteWizard(models.TransientModel):
    _name = 'bateria.gasto.reporte.wizard'
    _description = 'Asistente para Reporte de Gastos'

    fecha_inicio = fields.Date(string='Fecha de Inicio', required=True)
    fecha_fin = fields.Date(string='Fecha de Fin', required=True, default=fields.Date.context_today)

    def action_generar_reporte(self):
        domain = [('fecha', '>=', self.fecha_inicio), ('fecha', '<=', self.fecha_fin)]
        gastos = self.env['bateria.gasto.operativo'].search(domain, order='fecha asc')
        if not gastos:
            raise UserError("No se encontraron gastos en este rango de fechas.")
        return self.env.ref('bateria_reportes.action_reporte_diario_gastos').report_action(gastos)