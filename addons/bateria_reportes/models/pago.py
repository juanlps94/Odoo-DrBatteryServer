from odoo import models, fields, api

class BateriaPago(models.Model):
    _name = 'bateria.pago'
    _description = 'Pago de Orden de Venta'

    tarifa_ids = fields.One2many('bateria.producto.tarifa', 'producto_id', string='Reglas de Precio')

    orden_venta_id = fields.Many2one('bateria.orden.venta', string='Orden de Venta', ondelete='cascade')
    fecha_pago = fields.Date(string='Fecha de pago', default=fields.Date.today)
    monto = fields.Float(string='Monto Pagado', required=True)
    
    moneda = fields.Selection(
        [('usd', 'USD'), ('bs', 'Bs')],
        string='Moneda', required=True, default='usd'
    )

    tasa_cambio = fields.Float(string='Tasa (Bs/$)', default=1.0)

    tipo_pago = fields.Selection(
        [
            ('efectivo', 'Efectivo'),
            ('pago_movil', 'Pago Móvil'),
            ('zelle', 'Zelle/Transferencia'),
            ('cashea', 'Cashea'),
            ('punto', 'Punto de Venta'),
            ('saldo_favor', '🔄 Saldo a Favor (Reintegro)') # 👇 NUEVA OPCIÓN AÑADIDA 👇
        ],
        string='Método de Pago', required=True, default='efectivo'
    )

    referencia_banco = fields.Char(string='Ref. Operación')
    banco = fields.Char(string='Banco / Entidad') 
    serial_billetes = fields.Text(string='Seriales de Billetes')

    detalle_visual = fields.Char(string='Detalle Pago', compute='_compute_detalle_visual', store=True)

    # 👇 AQUÍ AGREGAMOS LOS CAMPOS DUALES 👇
    monto_usd = fields.Float(string='Abono ($)', compute='_compute_montos_duales', store=True)
    monto_bs = fields.Float(string='Abono (Bs)', compute='_compute_montos_duales', store=True)

    # 👇 NUEVOS CAMPOS: SALDOS RESTANTES EN TIEMPO REAL 👇
    saldo_restante_usd = fields.Float(string='Resta ($)', compute='_compute_saldo_restante')
    saldo_restante_bs = fields.Float(string='Resta (Bs)', compute='_compute_saldo_restante')

    @api.onchange('orden_venta_id')
    def _onchange_orden_moneda(self):
        if self.orden_venta_id:
            self.moneda = self.orden_venta_id.moneda
            if self.orden_venta_id.usar_tasa_personalizada:
                self.tasa_cambio = self.orden_venta_id.tasa_cambio
            else:
                self.tasa_cambio = self.orden_venta_id.tasa_bcv

    @api.depends('tipo_pago', 'moneda', 'referencia_banco', 'banco', 'serial_billetes')
    def _compute_detalle_visual(self):
        for pago in self:
            metodo = pago.tipo_pago.replace('_', ' ').title() # Pone "Pago Movil" bonito
            moneda_txt = "($)" if pago.moneda == 'usd' else "(Bs)"
            
            texto = ""
            
            # CASO 1: PAGO MÓVIL (Aquí agregamos el Banco)
            if pago.tipo_pago == 'pago_movil':
                banco_nom = pago.banco or 'S/B'
                ref = pago.referencia_banco or 'S/N'
                # Ej: "Pago Movil (Bs) - Banesco: 123456"
                texto = f"{metodo} {moneda_txt} - {banco_nom}: {ref}"

            # CASO 2: EFECTIVO
            elif pago.tipo_pago == 'efectivo':
                if pago.moneda == 'usd':
                    texto = f"Efectivo ($): {pago.serial_billetes or 'S/N'}"
                else:
                    texto = "Efectivo (Bs)"
                    
            # CASO 3: SALDO A FAVOR (REINTEGRO)
            elif pago.tipo_pago == 'saldo_favor':
                ref = pago.referencia_banco or 'Reintegro'
                texto = f"Saldo a Favor {moneda_txt} (Origen: {ref})"

            # CASO 4: OTROS (Zelle, Punto, Cashea)
            else:
                ref = pago.referencia_banco or 'S/N'
                texto = f"{metodo} {moneda_txt}: {ref}"

            pago.detalle_visual = texto

    # 👇 AQUÍ AGREGAMOS LA FUNCIÓN MATEMÁTICA PARA LOS DUALES AL FINAL 👇
    @api.depends('monto', 'moneda', 'tasa_cambio')
    def _compute_montos_duales(self):
        for p in self:
            tasa = p.tasa_cambio if p.tasa_cambio > 0 else 1.0
            if p.moneda == 'usd':
                p.monto_usd = p.monto
                p.monto_bs = p.monto * tasa
            else:
                p.monto_bs = p.monto
                p.monto_usd = p.monto / tasa

    # 👇 NUEVA FUNCIÓN MATEMÁTICA PARA EL RESTANTE 👇
    @api.depends('orden_venta_id.saldo_pendiente', 'orden_venta_id.tasa_aplicada')
    def _compute_saldo_restante(self):
        for pago in self:
            if not pago.orden_venta_id:
                pago.saldo_restante_usd = 0.0
                pago.saldo_restante_bs = 0.0
                continue
            
            tasa = pago.orden_venta_id.tasa_aplicada if pago.orden_venta_id.tasa_aplicada > 0 else 1.0
            saldo = pago.orden_venta_id.saldo_pendiente
            
            if pago.orden_venta_id.moneda == 'usd':
                pago.saldo_restante_usd = saldo
                pago.saldo_restante_bs = saldo * tasa
            else:
                pago.saldo_restante_usd = saldo / tasa
                pago.saldo_restante_bs = saldo