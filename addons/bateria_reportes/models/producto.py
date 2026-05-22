import base64
import csv
import io
from datetime import datetime
from odoo import models, fields, api
from odoo.exceptions import UserError

# =================================================================================
# 1. MOTOR DE SERIALES (ESTO SUBE EL STOCK DE BATERÍAS)
# =================================================================================
class BateriaSerial(models.Model):
    _name = 'bateria.serial'
    _description = 'Seriales Únicos de Batería'
    _rec_name = 'nombre'
    
    _order = 'fecha_ingreso ASC, id ASC'

    nombre = fields.Char(string='Número de Serial', required=True)
    producto_id = fields.Many2one('bateria.producto', string='Modelo', required=True,)
    ubicacion_id = fields.Many2one('bateria.ubicacion', string='Almacén de Ingreso', required=True)
    estado = fields.Selection([('disponible', 'Disponible'), ('vendido', 'Vendido')], default='disponible')
    orden_venta_id = fields.Many2one('bateria.orden.venta', string='Factura', readonly=True)

    cliente_id = fields.Many2one('bateria.cliente', related='orden_venta_id.cliente_id', store=True, string='Cliente')

    fecha_ingreso = fields.Date(string='Fecha de Ingreso', default=fields.Date.context_today, required=True)
    fecha_vencimiento = fields.Date(string='Vence el', compute='_compute_vencimiento', store=True)
    meses_restantes = fields.Integer(string='Meses Vida Útil', compute='_compute_vencimiento', store=True)

    _sql_constraints = [('serial_unique', 'unique(nombre)', '¡Este número de serial ya fue ingresado!')]

    @api.depends('fecha_ingreso')
    def _compute_vencimiento(self):
        from dateutil.relativedelta import relativedelta
        for s in self:
            if s.fecha_ingreso:
                s.fecha_vencimiento = s.fecha_ingreso + relativedelta(months=18)
                hoy = fields.Date.context_today(self)
                diff = (s.fecha_vencimiento.year - hoy.year) * 12 + s.fecha_vencimiento.month - hoy.month
                s.meses_restantes = diff if diff > 0 else 0
            else:
                s.fecha_vencimiento = False
                s.meses_restantes = 18

    @api.model_create_multi
    def create(self, vals_list):
        seriales = super(BateriaSerial, self).create(vals_list)
        for s in seriales:
            vencimiento_str = s.fecha_vencimiento.strftime('%d/%m/%Y') if s.fecha_vencimiento else 'Sin fecha'
            
            # Al crear un serial, se genera el ingreso automático en el inventario global
            self.env['bateria.inventario'].create({
                'fecha': fields.Datetime.now(),
                'tipo_movimiento': 'entrada',
                'producto_id': s.producto_id.id,
                'cantidad': 1,
                'ubicacion_id': s.ubicacion_id.id,
                'fecha_vencimiento': s.fecha_vencimiento,
                'nota': f'Ingreso de batería - Serial: {s.nombre} | Vence el: {vencimiento_str}'
            })
        return seriales

# =================================================================================
# 2. CATÁLOGO DE PRODUCTOS (HÍBRIDO: BATERÍAS Y ACCESORIOS)
# =================================================================================
class BateriaProducto(models.Model):
    _name = 'bateria.producto'
    _description = 'Catálogo de Modelos de Baterías y Accesorios'
    _rec_name = 'nombre'

    imagen = fields.Image(string="Foto del Modelo", max_width=1024, max_height=1024)
    nombre = fields.Char(string='Nombre del Producto', required=True)
    codigo_rfid = fields.Char(string='Código RFID')
    
    requiere_serial = fields.Boolean(string='¿Requiere Serial? (Baterías)', default=True, help="Desmarca esto para vender cables, terminales de ojal, refrigerantes, etc.")
    
    stock_minimo = fields.Integer(string='Punto de Reorden (Alerta Mínima)', default=10, help="El sistema te alertará si el stock baja de este número.")
    stock_bi_actual = fields.Integer(string='Stock Real', compute='_compute_stock_bi')


    def action_abrir_wizard_fechas(self):
        return {
            'name': 'Corregir Fechas de Ingreso',
            'type': 'ir.actions.act_window',
            'res_model': 'bateria.update.date.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_producto_id': self.id,
                'default_fecha_erronea': fields.Date.context_today(self)
            }
        }

    def _compute_stock_bi(self):
        for p in self:
            if p.requiere_serial:
                p.stock_bi_actual = self.env['bateria.serial'].search_count([
                    ('producto_id', '=', p.id),
                    ('estado', '=', 'disponible')
                ])
            else:
                ingresos = sum(self.env['bateria.inventario'].search([('producto_id', '=', p.id), ('tipo_movimiento', '=', 'entrada')]).mapped('cantidad'))
                salidas = sum(self.env['bateria.inventario'].search([('producto_id', '=', p.id), ('tipo_movimiento', '=', 'salida')]).mapped('cantidad'))
                p.stock_bi_actual = ingresos - salidas
                
    precio_base_usd = fields.Float(string='Precio Venta ($)', required=True, default=0.0)
    precio_bs = fields.Float(string='Precio en Bs (USDT)', compute='_compute_precio_bs', inverse='_inverse_precio_bs')

    serial_ids = fields.One2many('bateria.serial', 'producto_id', string='Historial de Seriales Físicos')
    movimiento_ids = fields.One2many('bateria.inventario', 'producto_id', string='Historial de Movimientos')
    
    alias_ids = fields.One2many('bateria.producto.alias', 'producto_id', string='Sinónimos / Nombres de Proveedor')
    
    stock_actual = fields.Integer(string='Stock Total', compute='_compute_stock_zonas')
    stock_racksito = fields.Integer(string='Disponibles en Racksito', compute='_compute_stock_zonas')
    stock_galpon = fields.Integer(string='Disponibles en Galpón', compute='_compute_stock_zonas')
    
    tarifa_ids = fields.One2many('bateria.producto.tarifa', 'producto_id', string='Reglas de Precio')

    _sql_constraints = [('nombre_unique', 'unique(nombre)', '¡Ya existe un modelo con este nombre!')]

    def _get_tasa_usdt(self):
        tasa_str = self.env['ir.config_parameter'].sudo().get_param('bateria.tasa_usdt', default='1.0')
        try: tasa = float(tasa_str)
        except: tasa = 1.0
        return tasa if tasa > 0 else 1.0
    
    tasa_usdt_actual = fields.Float(string="Tasa USDT Actual", compute="_compute_tasa_usdt_actual")

    def _compute_tasa_usdt_actual(self):
        tasa = self._get_tasa_usdt()
        for p in self:
            p.tasa_usdt_actual = tasa

    def action_actualizar_tasas_desde_producto(self):
        self.env['bateria.bcv.scraper'].actualizar_tasas_completas()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    @api.depends('serial_ids', 'serial_ids.estado', 'serial_ids.ubicacion_id', 'movimiento_ids', 'requiere_serial')
    def _compute_stock_zonas(self):
        for p in self:
            if p.requiere_serial:
                racksito = len(p.serial_ids.filtered(
                    lambda s: s.estado == 'disponible' and s.ubicacion_id and s.ubicacion_id.name and 'racksito' in s.ubicacion_id.name.lower()
                ))
                total = len(p.serial_ids.filtered(lambda s: s.estado == 'disponible'))
                
                p.stock_racksito = racksito
                p.stock_galpon = total - racksito
                p.stock_actual = total
            else:
                ingresos = sum(p.movimiento_ids.filtered(lambda m: m.tipo_movimiento == 'entrada').mapped('cantidad'))
                salidas = sum(p.movimiento_ids.filtered(lambda m: m.tipo_movimiento == 'salida').mapped('cantidad'))
                total_stock = ingresos - salidas
                
                p.stock_actual = total_stock
                p.stock_galpon = total_stock
                p.stock_racksito = 0

    @api.depends('precio_base_usd')
    def _compute_precio_bs(self):
        tasa = self._get_tasa_usdt()
        for p in self: p.precio_bs = p.precio_base_usd * tasa

    def _inverse_precio_bs(self):
        tasa = self._get_tasa_usdt()
        for p in self: p.precio_base_usd = p.precio_bs / tasa

    @api.onchange('precio_base_usd')
    def _onchange_precio_base_usd(self):
        tasa = self._get_tasa_usdt()
        if tasa > 1.0: self.precio_bs = self.precio_base_usd * tasa

    @api.onchange('precio_bs')
    def _onchange_precio_bs(self):
        tasa = self._get_tasa_usdt()
        if tasa > 1.0: self.precio_base_usd = self.precio_bs / tasa


# =================================================================================
# 3. TARIFAS
# =================================================================================
class BateriaTarifa(models.Model):
    _name = 'bateria.tarifa'
    _description = 'Listas de Precio / Tarifas'
    name = fields.Char(string='Nombre de la Tarifa', required=True)

class BateriaProductoTarifa(models.Model):
    _name = 'bateria.producto.tarifa'
    _description = 'Precio Específico por Tarifa'
    tarifa_id = fields.Many2one('bateria.tarifa', string='Tarifa', required=True)
    producto_id = fields.Many2one('bateria.producto', string='Producto', ondelete='cascade')
    precio = fields.Float(string='Precio Especial', required=True)
    moneda = fields.Selection([('usd', 'USD'), ('bs', 'Bs')], string='Moneda', default='bs', required=True)

# =================================================================================
# 4. DICCIONARIO DE ALIAS
# =================================================================================
class BateriaProductoAlias(models.Model):
    _name = 'bateria.producto.alias'
    _description = 'Diccionario de Sinónimos del Producto'

    name = fields.Char(string='Palabra Clave o Sinónimo', required=True, help="Ej: maya, mallas, ciclon 2x2")
    producto_id = fields.Many2one('bateria.producto', string='Producto Maestro', required=True, ondelete='cascade')

class BateriaProveedorTarifa(models.Model):
    _name = 'bateria.proveedor.tarifa'
    _description = 'Lista de Precios del Proveedor'

    proveedor_id = fields.Many2one('bateria.proveedor', string='Proveedor', required=True)
    producto_id = fields.Many2one('bateria.producto', string='Producto', required=True)
    precio = fields.Float(string='Precio de Compra', required=True)

# =================================================================================
# 5. ASISTENTE PARA IMPORTAR SERIALES CSV DESDE EL PRODUCTO (WIZARD)
# =================================================================================
class BateriaSerialImportWizard(models.TransientModel):
    _name = 'bateria.serial.import.wizard'
    _description = 'Asistente para Carga Masiva de Seriales CSV'

    producto_id = fields.Many2one('bateria.producto', string='Producto', required=True)
    archivo = fields.Binary(string='Archivo CSV', required=True)
    nombre_archivo = fields.Char(string='Nombre del Archivo')

    def action_importar_seriales(self):
        if not self.archivo:
            raise UserError('Debes seleccionar un archivo CSV primero.')

        file_content = base64.b64decode(self.archivo)
        
        try:
            try:
                texto = file_content.decode('utf-8-sig')
            except:
                texto = file_content.decode('latin-1')
            
            separador = ',' if ',' in texto[:100] else ';'
            reader = csv.DictReader(io.StringIO(texto), delimiter=separador)
            
            creados = 0
            actualizados = 0
            
            for row in reader:
                row_clean = {k.strip(): v.strip() for k, v in row.items() if k}
                
                serial_nombre = row_clean.get('Nombre')
                if not serial_nombre:
                    continue
                    
                estado_csv = row_clean.get('Estado', 'disponible').lower()
                ubicacion_csv = row_clean.get('Ubicacion', 'Racksito')
                
                # Extraer y formatear la fecha
                fecha_str = row_clean.get('Año') or row_clean.get('Año de fabricacion') or row_clean.get('Fecha Ingreso')
                fecha_final = fields.Date.context_today(self)
                
                if fecha_str:
                    fecha_str = fecha_str.strip()
                    if len(fecha_str) == 4 and fecha_str.isdigit():
                        fecha_final = f"{fecha_str}-01-01"
                    else:
                        try:
                            if '/' in fecha_str:
                                fecha_final = datetime.strptime(fecha_str, '%d/%m/%Y').date()
                            elif '-' in fecha_str:
                                fecha_final = datetime.strptime(fecha_str, '%Y-%m-%d').date()
                        except:
                            pass

                # Buscar si el serial YA EXISTE
                serial_existente = self.env['bateria.serial'].search([('nombre', '=', serial_nombre)], limit=1)
                
                if serial_existente:
                    # 💡 MODO ACTUALIZACIÓN: Si existe, solo le corregimos la fecha y la ubicación
                    ubicacion = self.env['bateria.ubicacion'].search([('nombre_completo', 'ilike', ubicacion_csv)], limit=1) or self.env['bateria.ubicacion'].search([('name', 'ilike', ubicacion_csv)], limit=1)
                    
                    valores_actualizar = {'fecha_ingreso': fecha_final}
                    if ubicacion:
                        valores_actualizar['ubicacion_id'] = ubicacion.id
                        
                    serial_existente.write(valores_actualizar)
                    actualizados += 1
                else:
                    # MODO CREACIÓN: Si no existe, lo crea
                    ubicacion = self.env['bateria.ubicacion'].search([('nombre_completo', 'ilike', ubicacion_csv)], limit=1) or self.env['bateria.ubicacion'].search([('name', 'ilike', ubicacion_csv)], limit=1)
                    
                    if not ubicacion:
                        raise UserError(f'🛑 El sistema no encontró la ubicación "{ubicacion_csv}" escrita en el CSV. Verifica que exista en tus ubicaciones.')

                    self.env['bateria.serial'].create({
                        'producto_id': self.producto_id.id,
                        'nombre': serial_nombre,
                        'estado': estado_csv,
                        'ubicacion_id': ubicacion.id,
                        'fecha_ingreso': fecha_final
                    })
                    creados += 1

        except Exception as e:
            raise UserError(f'🛑 Error al procesar el archivo CSV.\nDetalle técnico: {str(e)}')
        
        mensaje = f'¡Éxito! Se corrigió la fecha de {actualizados} seriales existentes y se crearon {creados} seriales nuevos.'
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
            'params': {'message': mensaje}
        }
    
# =================================================================================
# 6. ASISTENTE PARA CORREGIR FECHAS DE INGRESO ERRÓNEAS
# =================================================================================
class BateriaUpdateDateWizard(models.TransientModel):
    _name = 'bateria.update.date.wizard'
    _description = 'Asistente para Corregir Fechas de Seriales'

    producto_id = fields.Many2one('bateria.producto', string='Producto', required=True, readonly=True)
    fecha_erronea = fields.Date(string='Fecha Errónea (Buscar)', required=True, help="La fecha que el sistema puso por error.")
    fecha_correcta = fields.Date(string='Fecha Correcta (Nueva)', required=True, help="La fecha real en la que llegaron las baterías.")

    def action_actualizar_fechas(self):
        # 1. Buscar los seriales de este producto que tengan la fecha mala
        seriales = self.env['bateria.serial'].search([
            ('producto_id', '=', self.producto_id.id),
            ('fecha_ingreso', '=', self.fecha_erronea)
        ])
        
        if not seriales:
            raise UserError(f"No se encontraron seriales del modelo '{self.producto_id.nombre}' ingresados el {self.fecha_erronea.strftime('%d/%m/%Y')}.")
        
        cantidad = len(seriales)
        
        # 2. Escribir la fecha nueva (Esto disparará el recálculo de vencimiento automático)
        seriales.write({'fecha_ingreso': self.fecha_correcta})
        
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
            'params': {'message': f'¡Éxito! Se corrigió la fecha de ingreso y vencimiento de {cantidad} seriales.'}
        }
    
class BateriaReporteStockWizard(models.TransientModel):
    _name = 'bateria.reporte.stock.wizard'
    _description = 'Asistente para Reporte de Inventario de Baterías'

    ubicacion_id = fields.Many2one('bateria.ubicacion', string='Filtrar por Almacén (Opcional)', help="Si lo dejas en blanco, imprimirá el stock de todos los almacenes.")

    def action_imprimir_reporte(self):
        return self.env.ref('bateria_reportes.action_report_stock_baterias').report_action(self)