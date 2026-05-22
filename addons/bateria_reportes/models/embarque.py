from odoo import models, fields, api
from odoo.exceptions import UserError

class BateriaEmbarque(models.Model):
    _name = 'bateria.embarque'
    _description = 'Control de Importaciones Marítimas'
    _order = 'fecha_pedido desc, id desc'

    name = fields.Char(string='Referencia Interna', required=True, default='Nuevo', copy=False)
    
    # 👇 NUEVO: DATOS DEL PEDIDO Y FÁBRICA (SEGÚN PDF) 👇
    fabrica_id = fields.Many2one('bateria.proveedor', string='Fábrica / Proveedor', help="Ej: VASWORLD POWER CO.")
    referencia_fabrica = fields.Char(string='Referencia del Pedido', help="Ej: SOLICITUD DE PEDIDO Nº1 MARZO 2026")
    empresa_importadora = fields.Selection([
        ('don_juan', 'Corporación de Servicios Múltiples Don Juan, C.A.'),
        ('juan_andres', 'Juan Andres Cafe 33, C.A.'),
        ('jjs_2021', 'Inversiones J.J.S 2021, C.A.'),
        ('zolmala_2000', 'Inversiones Zolmala 2000, C.A.'),
        ('dr_battery', 'Dr Battery 33, C.A.')
    ], string='Empresa Importadora', default='don_juan')

    # LOGÍSTICA MARÍTIMA A GRAN ESCALA (CHINA)
    bl_booking = fields.Char(string='BL / Booking (Bill of Lading)')
    proveedor_flete_id = fields.Many2one('bateria.proveedor', string='Naviera / Forwarder')
    nombre_buque = fields.Char(string='Nombre del Buque (Vessel / Voyage)')
    puerto_origen = fields.Char(string='Puerto de Origen', default='Ningbo, China')
    puerto_destino = fields.Char(string='Puerto de Destino', default='Puerto Cabello, Venezuela')
    
    # CONTROL DE VOLUMEN Y PESO
    cantidad_contenedores = fields.Integer(string='Cantidad de Contenedores', default=1, required=True)
    numero_contenedor = fields.Char(string='IDs de Contenedores', help="Ej: TCNU1234567, MSCU7654321")
    
    peso_total_kg = fields.Float(string='Peso Total (KG)', compute='_compute_totales_lineas', store=True)
    peso_toneladas = fields.Float(string='Peso Total (Toneladas)', compute='_compute_totales_lineas', store=True)

    # Control de Tiempos Marítimos
    fecha_pedido = fields.Date(string='Fecha de Zarpe (ETD)', default=fields.Date.context_today, required=True)
    fecha_llegada_estimada = fields.Date(string='Llegada Estimada (ETA)')
    fecha_llegada_real = fields.Date(string='Llegada Real a Puerto', readonly=True)
    dias_transito = fields.Integer(string='Días en el Mar', compute='_compute_dias_transito', store=True)

    # Control Financiero (Fletes Marítimos, Nacionalización, etc)
    costo_flete = fields.Float(string='Costo Total de Importación ($)', required=True, default=0.0)
    total_baterias = fields.Integer(string='Total de Artículos', compute='_compute_totales_lineas', store=True)
    costo_por_bateria = fields.Float(string='Costo Flete x Artículo ($)', compute='_compute_totales_lineas', store=True)

    estado = fields.Selection([
        ('borrador', 'En Origen (China)'),
        ('en_transito', '🚢 Zarpó (En el Mar)'),
        ('entregado', '✅ En Puerto Destino / Nacionalizado'),
        ('cancelado', '❌ Cancelado')
    ], string='Estado', default='borrador')

    linea_ids = fields.One2many('bateria.embarque.linea', 'embarque_id', string='Modelos Solicitados')
    notas = fields.Text(string='Notas / Novedades Marítimas')

    @api.depends('fecha_pedido', 'fecha_llegada_real')
    def _compute_dias_transito(self):
        for r in self:
            if r.fecha_pedido and r.fecha_llegada_real:
                delta = r.fecha_llegada_real - r.fecha_pedido
                r.dias_transito = delta.days
            elif r.fecha_pedido and not r.fecha_llegada_real:
                hoy = fields.Date.context_today(self)
                delta = hoy - r.fecha_pedido
                r.dias_transito = delta.days if delta.days > 0 else 0
            else:
                r.dias_transito = 0

    @api.depends('costo_flete', 'linea_ids.cantidad', 'linea_ids.peso_total_kg')
    def _compute_totales_lineas(self):
        for r in self:
            total_qty = sum(l.cantidad for l in r.linea_ids)
            total_kg = sum(l.peso_total_kg for l in r.linea_ids)
            
            r.total_baterias = total_qty
            r.peso_total_kg = total_kg
            r.peso_toneladas = total_kg / 1000 if total_kg > 0 else 0.0
            
            if total_qty > 0 and r.costo_flete > 0:
                r.costo_por_bateria = r.costo_flete / total_qty
            else:
                r.costo_por_bateria = 0.0

    def action_en_transito(self):
        for r in self:
            if not r.linea_ids:
                raise UserError("Debes agregar al menos un artículo a la importación.")
            r.estado = 'en_transito'

    def action_recibir_embarque(self):
        for r in self:
            r.fecha_llegada_real = fields.Date.context_today(self)
            r.estado = 'entregado'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('bateria.embarque.seq') or 'IMP-0000'
        return super(BateriaEmbarque, self).create(vals_list)

class BateriaEmbarqueLinea(models.Model):
    _name = 'bateria.embarque.linea'
    _description = 'Detalle de Modelos en Embarque'

    embarque_id = fields.Many2one('bateria.embarque', ondelete='cascade')
    producto_id = fields.Many2one('bateria.producto', string='Descripción', required=True)
    
    # 👇 COLUMNAS IDÉNTICAS AL PDF 👇
    part_no = fields.Char(string='Part No.')
    unidad_medida = fields.Char(string='Unidad', default='UND')
    cantidad = fields.Integer(string='Cantidad', required=True, default=1)
    peso_unitario_kg = fields.Float(string='Peso Unitario (KG)', default=0.0)
    
    peso_total_kg = fields.Float(string='Total KG', compute='_compute_peso', store=True)

    @api.depends('cantidad', 'peso_unitario_kg')
    def _compute_peso(self):
        for l in self:
            l.peso_total_kg = l.cantidad * l.peso_unitario_kg