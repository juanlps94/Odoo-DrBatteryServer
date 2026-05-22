from odoo import models, fields, api

class CierreCaja(models.Model):
    _name = 'bateria.cierre.caja'
    _description = 'Cierre de Caja Diario'
    
    name = fields.Char(string='Referencia', default='Nuevo')
    fecha = fields.Date(string='Fecha', required=True, default=fields.Date.today)
    responsable_id = fields.Many2one('res.users', string='Responsable', required=True, default=lambda self: self.env.user)
    
    # Montos básicos
    efectivo_bs_apertura = fields.Float(string='Efectivo Bs Apertura', default=0.0)
    efectivo_bs_cierre_real = fields.Float(string='Cierre Real Bs', default=0.0)
    efectivo_usd_apertura = fields.Float(string='Efectivo $ Apertura', default=0.0)
    efectivo_usd_cierre_real = fields.Float(string='Cierre Real $', default=0.0)
    
    estado = fields.Selection([
        ('borrador', 'Borrador'),
        ('confirmado', 'Confirmado'),
        ('cancelado', 'Cancelado')
    ], string='Estado', default='borrador')
    
    observaciones = fields.Text(string='Observaciones')
    
    @api.model
    def create(self, vals):
        if vals.get('name', 'Nuevo') == 'Nuevo':
            vals['name'] = self.env['ir.sequence'].next_by_code('bateria.cierre.caja') or 'Nuevo'
        return super(CierreCaja, self).create(vals)