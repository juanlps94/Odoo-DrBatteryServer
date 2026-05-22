from odoo import models, fields, api

class BateriaVehiculo(models.Model):
    _name = 'bateria.vehiculo'
    _description = 'Flota de Vehículos'

    name = fields.Char(string='Placa', required=True)
    marca_modelo = fields.Char(string='Marca y Modelo')
    ano = fields.Char(string='Año')
    
    kilometraje_actual = fields.Float(string='Kilometraje Actual', help="Se actualiza automáticamente con los servicios.")
    
    servicio_ids = fields.One2many('bateria.vehiculo.servicio', 'vehiculo_id', string='Historial de Servicios')
    
    # 👇 NUEVO: SE TRAE TODO LO COMPRADO DIRECTAMENTE DESDE EL MÓDULO DE COMPRAS 👇
    compra_linea_ids = fields.One2many('bateria.compra.linea', 'vehiculo_id', string='Repuestos Comprados (Soporte)')
    
    gasto_total = fields.Float(string='Gasto Total ($)', compute='_compute_totales', store=True)
    litros_totales = fields.Float(string='Balance de Combustible (Lts)', compute='_compute_totales', store=True)

    @api.depends('servicio_ids.costo_total', 'servicio_ids.cantidad_litros', 'servicio_ids.litros_extraidos')
    def _compute_totales(self):
        for v in self:
            v.gasto_total = sum(s.costo_total for s in v.servicio_ids if s.tipo_servicio in ('gasolina', 'mantenimiento'))
            
            litros_echados = sum(s.cantidad_litros for s in v.servicio_ids if s.tipo_servicio == 'gasolina')
            litros_sacados = sum(s.litros_extraidos for s in v.servicio_ids if s.tipo_servicio == 'extraccion_gasolina')
            
            v.litros_totales = litros_echados - litros_sacados

class BateriaServicioVehiculo(models.Model):
    _name = 'bateria.vehiculo.servicio'
    _description = 'Registro de Servicios de Flota'
    _order = 'fecha desc'

    vehiculo_id = fields.Many2one('bateria.vehiculo', string='Vehículo', required=True)
    
    # 👇 NUEVO: TIPO DE SERVICIO DE EXTRACCIÓN 👇
    tipo_servicio = fields.Selection([
        ('gasolina', 'Carga de Gasolina'), 
        ('mantenimiento', 'Mantenimiento / Repuesto'),
        ('extraccion_gasolina', 'Extracción de Gasolina')
    ], string='Tipo de Registro', required=True, default='gasolina')
    
    fecha = fields.Date(string='Fecha', default=fields.Date.context_today)
    
    km_anterior = fields.Float(string='Kilometraje Anterior')
    km_actual = fields.Float(string='Kilometraje Actual', required=True)
    km_recorridos = fields.Float(string='Km Recorridos', compute='_compute_recorrido', store=True)
    
    cantidad_litros = fields.Float(string='Litros Surtidos')
    
    # 👇 NUEVOS CAMPOS PARA EXTRACCIÓN 👇
    litros_extraidos = fields.Float(string='Litros Extraídos (-)')
    mecanico = fields.Char(string='Mecánico Responsable')
    
    # Le quitamos el required=True porque la extracción no genera costo en $
    costo_total = fields.Float(string='Costo Total Pagado ($)')
    notas = fields.Text(string='Observaciones / Motivo')

    @api.onchange('vehiculo_id')
    def _onchange_vehiculo_id(self):
        if self.vehiculo_id:
            self.km_anterior = self.vehiculo_id.kilometraje_actual
            self.km_actual = self.vehiculo_id.kilometraje_actual

    @api.depends('km_anterior', 'km_actual')
    def _compute_recorrido(self):
        for rec in self:
            rec.km_recorridos = rec.km_actual - rec.km_anterior if rec.km_actual > rec.km_anterior else 0.0

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.km_actual > rec.vehiculo_id.kilometraje_actual:
                rec.vehiculo_id.kilometraje_actual = rec.km_actual
        return records