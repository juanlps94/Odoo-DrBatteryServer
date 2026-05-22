from odoo import models, fields, api

class CuentaPagar(models.Model):
    _name = 'bateria.cuenta.pagar'
    _description = 'Cuentas por Pagar'

    name = fields.Char(string='Referencia / Factura', required=True, placeholder="Ej: FAC-0012")
    fecha = fields.Date(string='Fecha', default=fields.Date.context_today)
    proveedor = fields.Char(string='Proveedor / Acreedor', required=True)
    concepto = fields.Char(string='Concepto', placeholder="Ej: Compra de chatarras, flete...")

    moneda = fields.Selection([('usd', 'USD'), ('bs', 'Bs')], string='Moneda', default='usd', required=True)
    monto_total = fields.Float(string='Monto Total de la Deuda', required=True)
    monto_pagado = fields.Float(string='Abonos Realizados', default=0.0)
    
    saldo_pendiente = fields.Float(string='Saldo Pendiente', compute='_compute_saldo', store=True)

    estado = fields.Selection([
        ('borrador', 'Por Pagar'),
        ('parcial', 'Pago Parcial'),
        ('pagado', 'Pagado')
    ], string='Estado', default='borrador', compute='_compute_estado', store=True)

    @api.depends('monto_total', 'monto_pagado')
    def _compute_saldo(self):
        for r in self:
            r.saldo_pendiente = r.monto_total - r.monto_pagado

    @api.depends('saldo_pendiente', 'monto_total', 'monto_pagado')
    def _compute_estado(self):
        for r in self:
            if r.monto_pagado >= r.monto_total and r.monto_total > 0:
                r.estado = 'pagado'
            elif r.monto_pagado > 0:
                r.estado = 'parcial'
            else:
                r.estado = 'borrador'

    # condicion de pago 
    condicion_pago = fields.Selection([
        ('contado', 'De Contado'),
        ('credito_15', 'Crédito 15 Días'),
        ('credito_30', 'Crédito 30 Días'),
        ('credito_45', 'Crédito 45 Días'),
    ], string='Condiciones de Pago', default='contado')
    
    es_activo_fijo = fields.Boolean(string='¿Es un Activo de la Empresa?', help="Márcalo si esta compra debe ir al inventario de activos.")
    activo_generado = fields.Boolean(string='Activo Generado', default=False, copy=False)

    # 1. FUNCIÓN AUTOMÁTICA AL CREAR NUEVA COMPRA
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.es_activo_fijo and not rec.activo_generado:
                rec._crear_activo_automatico()
        return records

    # 2. FUNCIÓN AUTOMÁTICA AL EDITAR/GUARDAR UNA COMPRA EXISTENTE
    def write(self, vals):
        res = super().write(vals)
        for rec in self:
            if rec.es_activo_fijo and not rec.activo_generado:
                rec._crear_activo_automatico()
        return res

    # 3. EL MOTOR QUE HACE LA MAGIA SILENCIOSAMENTE
    def _crear_activo_automatico(self):
        self.env['bateria.activo'].create({
            'name': f"Activo (Ref: {self.name or 'N/A'}) - {self.proveedor or ''}",
            'valor_compra': self.monto_total,
            'fecha_adquisicion': self.fecha,
            'compra_id': self.id,
        })
        self.activo_generado = True