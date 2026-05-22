from odoo import models, fields, api
from odoo.exceptions import UserError

class BateriaLibroMayor(models.Model):
    _name = 'bateria.libro.mayor'
    _description = 'Libro Mayor de Transacciones'
    _order = 'fecha desc, id desc'

    # 👇 AÑADIDO COMPANY_ID 👇
    company_id = fields.Many2one('res.company', string='Compañía', required=True, default=lambda self: self.env.company)

    tipo_documento = fields.Selection([
        ('nota_entrega', 'Nota de Entrega / Admin'), 
        ('factura', 'Factura Fiscal')
    ], string='Clasificación', required=True, default='nota_entrega')
    

    name = fields.Char(string='Comprobante', default='Nuevo')
    fecha = fields.Date(string='Fecha', required=True, default=fields.Date.context_today)
    caja_id = fields.Many2one('bateria.caja', string='Caja / Banco', required=True)
    referencia = fields.Char(string='Referencia / Nro. Operación')
    concepto = fields.Char(string='Concepto')
    tipo_movimiento = fields.Selection([('ingreso', 'Ingreso (+)'), ('egreso', 'Egreso (-)')], string='Tipo', required=True)
    monto = fields.Float(string='Monto', required=True)
    moneda = fields.Selection([('usd', 'USD'), ('bs', 'Bs'), ('eur', 'EUR')], string='Moneda')
    estado = fields.Selection([('pendiente', 'Pendiente de Conciliar'), ('conciliado', 'Conciliado')], string='Estado', default='pendiente')
    compra_id = fields.Many2one('bateria.compra', string='Compra de Origen')

    motivo_pendiente = fields.Char(string='Motivo del Estatus', compute='_compute_motivo_pendiente')

    @api.depends('estado', 'caja_id', 'referencia')
    def _compute_motivo_pendiente(self):
        for mov in self:
            if mov.estado == 'conciliado':
                mov.motivo_pendiente = ''
                continue
            if not mov.referencia:
                mov.motivo_pendiente = '❌ Sin número de referencia'
                continue
            linea_falta = self.env['bateria.auditor.bdt.linea'].search([
                ('referencia', '=', mov.referencia), ('ubicacion_faltante', '=', 'falta_en_banco'), ('auditor_id.caja_id', '=', mov.caja_id.id)
            ], limit=1)
            if linea_falta:
                mov.motivo_pendiente = '📅 Fuera de corte'
                continue
            auditoria_abierta = self.env['bateria.auditor.bdt'].search([('caja_id', '=', mov.caja_id.id), ('estado', '=', 'analizado')], limit=1)
            if auditoria_abierta:
                mov.motivo_pendiente = '⏳ Esperando Cierre de Conciliación'
            else:
                mov.motivo_pendiente = '📄 Falta subir Estado de Cuenta'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if isinstance(vals, dict) and vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('bateria.libro.mayor.seq') or 'LM-0000'
        return super(BateriaLibroMayor, self).create(vals_list)

class BateriaCuentaContable(models.Model):
    _name = 'bateria.cuenta.contable'
    _description = 'Catálogo de Cuentas VEN-NIF'
    _rec_name = 'nombre_completo'

    # 👇 AÑADIDO COMPANY_ID 👇
    company_id = fields.Many2one('res.company', string='Compañía', default=lambda self: self.env.company, help="Dejar vacío si es una cuenta global")

    codigo = fields.Char(string='Código', required=True, help="Ej: 1.1.01.01")
    name = fields.Char(string='Nombre de la Cuenta', required=True)
    nombre_completo = fields.Char(compute='_compute_nombre', store=True)
    tipo = fields.Selection([('1', '1 - Activo'), ('2', '2 - Pasivo'), ('3', '3 - Patrimonio'), ('4', '4 - Ingresos'), ('5', '5 - Costos'), ('6', '6 - Gastos')], string='Clase de Cuenta', required=True)
    padre_id = fields.Many2one('bateria.cuenta.contable', string='Cuenta Padre (Agrupadora)')

    @api.depends('codigo', 'name')
    def _compute_nombre(self):
        for r in self: r.nombre_completo = f"{r.codigo} - {r.name}"

class BateriaCaja(models.Model):
    _name = 'bateria.caja'
    _description = 'Cuentas Bancarias y Cajas'

    # 👇 AÑADIDO COMPANY_ID 👇
    company_id = fields.Many2one('res.company', string='Compañía Perteneciente', required=True, default=lambda self: self.env.company)

    name = fields.Char(string='Nombre de la Caja/Banco', required=True)
    tipo = fields.Selection([('banco', 'Cuenta Bancaria'), ('efectivo', 'Caja de Efectivo')], required=True)
    cuenta_contable_id = fields.Many2one('bateria.cuenta.contable', string='Cuenta Contable Asociada', required=True)
    moneda = fields.Selection([('bs', 'Bolívares'), ('usd', 'Dólares'), ('eur', 'Euros')], required=True, default='bs')
    saldo_real = fields.Float(string='Saldo en Banco/Caja', default=0.0)

class BateriaExtracto(models.Model):
    _name = 'bateria.extracto'
    _description = 'Extracto de Conciliación'

    name = fields.Char(string='Referencia del Extracto', required=True, copy=False, default='Nueva Conciliación')
    caja_id = fields.Many2one('bateria.caja', string='Banco / Caja', required=True)
    fecha = fields.Date(string='Fecha de Cierre', default=fields.Date.context_today)
    estado = fields.Selection([('borrador', 'En Proceso'), ('validado', 'Conciliado y Cerrado')], default='borrador', string='Estado')
    linea_ids = fields.One2many('bateria.extracto.linea', 'extracto_id', string='Movimientos')

class BateriaExtractoLinea(models.Model):
    _name = 'bateria.extracto.linea'
    _description = 'Línea de Extracto'

    extracto_id = fields.Many2one('bateria.extracto', ondelete='cascade')
    fecha = fields.Date(required=True)
    concepto = fields.Char(string='Descripción del Banco', required=True)
    monto = fields.Float(string='Monto (Real en Banco)', required=True)
    pago_id = fields.Many2one('bateria.pago', string='Pago en Sistema (Match)')

class BateriaPagoExtension(models.Model):
    _inherit = 'bateria.pago'
    estado_conciliacion = fields.Selection([('pendiente', 'Pendiente en Banco'), ('conciliado', 'Conciliado')], default='pendiente', string='Estado Contable')

class BateriaAuditorBdt(models.Model):
    _name = 'bateria.auditor.bdt'
    _description = 'Auditor y Conciliador de Bancos'

    name = fields.Char(string='Descripción', default='Conciliación de Excel')
    fecha = fields.Datetime(string='Fecha', default=fields.Datetime.now)
    caja_id = fields.Many2one('bateria.caja', string='Banco / Caja a Auditar', required=True)
    archivo = fields.Binary(string='Archivo (Excel / CSV)', required=True)
    nombre_archivo = fields.Char(string='Nombre del Archivo')
    estado = fields.Selection([('borrador', 'Sin Analizar'), ('analizado', 'Analizado'), ('validado', 'Conciliación Cerrada')], string='Estado', default='borrador')
    total_ingresos_banco = fields.Float(string='Total Ingresos (Banco)')
    total_egresos_banco = fields.Float(string='Total Egresos Generales')
    total_comisiones_banco = fields.Float(string='Total Comisiones Cobradas')
    linea_faltante_ids = fields.One2many('bateria.auditor.bdt.linea', 'auditor_id', string='⚠️ Diferencias Encontradas')

    def action_analizar_archivo(self):
        import base64
        import io
        import csv
        for rec in self:
            if not rec.archivo: raise UserError("Debe subir un archivo.")
            rec.linea_faltante_ids.unlink() 
            filas = []
            nombre = rec.nombre_archivo.lower() if rec.nombre_archivo else ''
            file_content = base64.b64decode(rec.archivo)

            try:
                if nombre.endswith('.csv'):
                    try: texto = file_content.decode('utf-8-sig')
                    except: texto = file_content.decode('latin-1')
                    separador = ',' if ',' in texto[:100] else ';'
                    reader = csv.reader(io.StringIO(texto), delimiter=separador)
                    filas = list(reader)
                else:
                    import openpyxl
                    wb = openpyxl.load_workbook(filename=io.BytesIO(file_content), data_only=True)
                    sheet = wb.active
                    for row in sheet.iter_rows(values_only=True): filas.append(row)
            except Exception as e:
                raise UserError(f"Error al leer el archivo. Detalle: {str(e)}")

            datos_mayor = []
            movimientos_internos = self.env['bateria.libro.mayor'].search([('estado', '=', 'pendiente'), ('caja_id', '=', rec.caja_id.id)])
            for mov in movimientos_internos:
                if mov.referencia:
                    ref_izq = str(mov.referencia).strip()
                    datos_mayor.append({'ref': ref_izq, 'texto_busqueda': f"{ref_izq} - {mov.concepto}", 'fila_sistema': [mov.fecha, '', mov.caja_id.name, ref_izq, mov.monto, mov.concepto], 'mov_id': mov.id})
            
            datos_banco = []
            sum_ingresos, sum_egresos, sum_comisiones = 0.0, 0.0, 0.0
            palabras_comision = ['comision', 'comisión', 'igtf', 'itf', 'mantenimiento', 'iva', 'retencion', 'retención', 'com.', 'tarifa']

            for fila in filas:
                if not fila or not any(fila): continue
                fila_str = [str(col).strip() if col is not None else '' for col in fila]
                ref_der, concepto_der, monto_str, monto_float, es_ingreso = '', '', '0', 0.0, True

                if len(fila_str) >= 8 and fila_str[0].isdigit():
                    ref_der, concepto_der = fila_str[2].replace('.0', ''), fila_str[4]
                    debito = float(fila_str[5].replace(',', '.')) if fila_str[5] else 0.0
                    credito = float(fila_str[6].replace(',', '.')) if fila_str[6] else 0.0
                    if debito > 0: monto_float, es_ingreso = debito, False
                    else: monto_float, es_ingreso = credito, True
                    monto_str = str(monto_float)
                elif len(fila_str) >= 5 and ('-' in fila_str[0] or '/' in fila_str[0]):
                    ref_der, concepto_der, monto_str = fila_str[1].replace('.0', ''), fila_str[2], str(fila_str[3])
                    try:
                        monto_float = float(monto_str.replace(',', ''))
                        es_ingreso, monto_float = monto_float > 0, abs(monto_float)
                    except: monto_float = 0.0
                elif len(fila_str) > 9:
                    ref_der = fila_str[9].replace('.0', '')
                    monto_str = str(fila_str[10]) if len(fila_str) > 10 else '0'
                    concepto_der = fila_str[11] if len(fila_str) > 11 else ''
                    try: monto_float = float(monto_str)
                    except: monto_float = 0.0

                if ref_der and ref_der.lower() not in ('referencia', 'none', 'ref', ''):
                    es_comision_bancaria = any(kw in concepto_der.lower() for kw in palabras_comision) and not es_ingreso
                    datos_banco.append({'ref': ref_der, 'texto_busqueda': f"{ref_der} - {concepto_der}", 'monto_str': monto_str, 'monto_float': monto_float, 'concepto': concepto_der, 'es_comision': es_comision_bancaria, 'es_ingreso': es_ingreso})
                    if es_ingreso: sum_ingresos += monto_float
                    elif es_comision_bancaria: sum_comisiones += monto_float
                    else: sum_egresos += monto_float

            rec.total_ingresos_banco, rec.total_comisiones_banco, rec.total_egresos_banco = sum_ingresos, sum_comisiones, sum_egresos
            lineas_faltantes = []
            
            for d_mayor in datos_mayor:
                encontrado = False
                ref_mayor_limpia = d_mayor['ref'].lstrip('0').lower() 
                for d_banco in datos_banco:
                    ref_banco_limpia = d_banco['ref'].lstrip('0').lower()
                    if (ref_mayor_limpia == ref_banco_limpia and ref_mayor_limpia != '') or (ref_mayor_limpia in d_banco['texto_busqueda'].lower()) or (ref_banco_limpia in d_mayor['texto_busqueda'].lower()):
                        encontrado = True; break
                if not encontrado:
                    f_sis = d_mayor['fila_sistema']
                    lineas_faltantes.append((0, 0, {'ubicacion_faltante': 'falta_en_banco', 'banco_destino': str(f_sis[2]) if f_sis[2] else 'Registro Interno', 'referencia': d_mayor['ref'], 'monto_float': float(f_sis[4]) if f_sis[4] else 0.0, 'concepto': str(f_sis[5]) if f_sis[5] else ''}))
            
            for d_banco in datos_banco:
                encontrado = False
                ref_banco_limpia = d_banco['ref'].lstrip('0').lower()
                for d_mayor in datos_mayor:
                    ref_mayor_limpia = d_mayor['ref'].lstrip('0').lower()
                    if (ref_banco_limpia == ref_mayor_limpia and ref_banco_limpia != '') or (ref_banco_limpia in d_mayor['texto_busqueda'].lower()) or (ref_mayor_limpia in d_banco['texto_busqueda'].lower()):
                        encontrado = True; break
                if not encontrado:
                    tipo_falta = 'comision' if d_banco['es_comision'] else 'falta_en_mayor'
                    lineas_faltantes.append((0, 0, {'ubicacion_faltante': tipo_falta, 'banco_destino': 'Estado de Cuenta', 'referencia': d_banco['ref'], 'monto_float': d_banco['monto_float'], 'concepto': d_banco['concepto']}))
                        
            rec.linea_faltante_ids, rec.estado = lineas_faltantes, 'analizado'

    def action_registrar_comisiones(self):
        for rec in self:
            comisiones = rec.linea_faltante_ids.filtered(lambda l: l.ubicacion_faltante == 'comision')
            if not comisiones: raise UserError("No hay comisiones pendientes por registrar.")
            total_comisiones = sum(c.monto_float for c in comisiones)
            self.env['bateria.libro.mayor'].create({'fecha': rec.fecha.date() if rec.fecha else fields.Date.context_today(self), 'caja_id': rec.caja_id.id, 'referencia': f"COMISIONES-{rec.name[:10]}", 'concepto': f"Registro agrupado de Comisiones / IGTF / Impuestos detectados", 'tipo_movimiento': 'egreso', 'monto': total_comisiones, 'moneda': rec.caja_id.moneda})
            comisiones.unlink()
            return {'effect': {'fadeout': 'slow', 'message': f'¡Excelente! Se registraron {total_comisiones:,.2f} en gastos bancarios.', 'type': 'rainbow_man'}}

    def action_validar_conciliacion(self):
        for rec in self:
            movimientos_pendientes = self.env['bateria.libro.mayor'].search([('caja_id', '=', rec.caja_id.id), ('estado', '=', 'pendiente')])
            referencias_con_error = rec.linea_faltante_ids.filtered(lambda l: l.ubicacion_faltante == 'falta_en_banco').mapped('referencia')
            movimientos_exitosos = movimientos_pendientes.filtered(lambda m: m.referencia not in referencias_con_error)
            movimientos_exitosos.write({'estado': 'conciliado'})
            rec.estado = 'validado'
            return {'effect': {'fadeout': 'slow', 'message': f'¡Brutal! Se han conciliado {len(movimientos_exitosos)} transacciones automáticamente.', 'type': 'rainbow_man'}}

class BateriaAuditorBdtLinea(models.Model):
    _name = 'bateria.auditor.bdt.linea'
    _description = 'Línea de Diferencia Conciliación'

    auditor_id = fields.Many2one('bateria.auditor.bdt', ondelete='cascade')
    ubicacion_faltante = fields.Selection([('falta_en_banco', 'Falta en Banco (No cayó)'), ('falta_en_mayor', 'Falta en Sistema (Registrar)'), ('comision', '💸 Comisión Bancaria / IGTF')], string='Clasificación')
    banco_destino = fields.Char(string='Ubicación')
    referencia = fields.Char(string='Referencia (REF)')
    monto_float = fields.Float(string='Monto')
    concepto = fields.Char(string='Concepto')

class BateriaReporteLibroMayorWizard(models.TransientModel):
    _name = 'bateria.reporte.libro.mayor.wizard'
    _description = 'Wizard para Reporte de Libro Mayor'

    # 👇 NUEVO: Detecta automáticamente tu empresa actual 👇
    company_id = fields.Many2one('res.company', string='Compañía', required=True, default=lambda self: self.env.company)

    fecha_inicio = fields.Date(string='Fecha Inicio', required=True, default=fields.Date.context_today)
    fecha_fin = fields.Date(string='Fecha Fin', required=True, default=fields.Date.context_today)
    caja_id = fields.Many2one('bateria.caja', string='Banco / Caja Específica', help='Dejar vacío para imprimir todos los bancos')

    def action_imprimir_reporte(self):
        # 👇 NUEVO: Agregamos el filtro de company_id al buscador 👇
        domain = [
            ('fecha', '>=', self.fecha_inicio), 
            ('fecha', '<=', self.fecha_fin),
            ('company_id', '=', self.company_id.id)
        ]
        
        if self.caja_id: 
            domain.append(('caja_id', '=', self.caja_id.id))
            
        movimientos = self.env['bateria.libro.mayor'].search(domain, order='fecha asc, id asc')
        
        if not movimientos: 
            raise UserError("No se encontraron transacciones contables para esta empresa en el rango seleccionado.")
            
        return self.env.ref('bateria_reportes.action_report_libro_mayor').with_context(
            fecha_inicio=self.fecha_inicio, 
            fecha_fin=self.fecha_fin, 
            banco=self.caja_id.name if self.caja_id else 'TODOS'
        ).report_action(movimientos)
    
class BateriaDiarioContable(models.Model):
    _name = 'bateria.diario'
    _description = 'Diarios Contables'

    # 👇 AÑADIDO COMPANY_ID 👇
    company_id = fields.Many2one('res.company', string='Compañía', required=True, default=lambda self: self.env.company)

    name = fields.Char(string='Nombre del Diario', required=True)
    codigo = fields.Char(string='Código Corto', required=True, size=5, help="Ej: VEN, COM, BCO")
    tipo = fields.Selection([('venta', 'Ventas'), ('compra', 'Compras / Gastos'), ('efectivo', 'Efectivo'), ('banco', 'Banco'), ('general', 'Operaciones Diversas')], string='Tipo de Diario', required=True)
    cuenta_defecto_id = fields.Many2one('bateria.cuenta.contable', string='Cuenta Contable por Defecto')

class BateriaAsientoContable(models.Model):
    _name = 'bateria.asiento'
    _description = 'Asiento Contable (Journal Entry)'
    _order = 'fecha desc, id desc'

    # 👇 AÑADIDO COMPANY_ID 👇
    company_id = fields.Many2one('res.company', string='Compañía', required=True, default=lambda self: self.env.company)

    name = fields.Char(string='Número de Asiento', readonly=True, default='/')
    fecha = fields.Date(string='Fecha Contable', required=True, default=fields.Date.context_today)
    referencia = fields.Char(string='Referencia / Nro. Documento')
    diario_id = fields.Many2one('bateria.diario', string='Diario', required=True)
    estado = fields.Selection([('borrador', 'Borrador'), ('asentado', 'Asentado')], string='Estado', default='borrador')
    linea_ids = fields.One2many('bateria.apunte', 'asiento_id', string='Apuntes Contables')
    total_debe = fields.Float(string='Total Debe', compute='_compute_totales', store=True)
    total_haber = fields.Float(string='Total Haber', compute='_compute_totales', store=True)

    @api.depends('linea_ids.debe', 'linea_ids.haber')
    def _compute_totales(self):
        for asiento in self:
            asiento.total_debe = sum(l.debe for l in asiento.linea_ids)
            asiento.total_haber = sum(l.haber for l in asiento.linea_ids)

    def action_asentar(self):
        for asiento in self:
            if not asiento.linea_ids: raise UserError("El asiento contable debe tener al menos una línea.")
            if round(asiento.total_debe, 2) != round(asiento.total_haber, 2): raise UserError(f"¡El asiento no cuadra! El Debe no es igual al Haber.")
            if asiento.name == '/':
                secuencia = self.env['ir.sequence'].next_by_code('bateria.asiento.seq') or 'AST-0000'
                asiento.name = f"{asiento.diario_id.codigo}-{secuencia}"
            asiento.estado = 'asentado'

class BateriaApunteContable(models.Model):
    _name = 'bateria.apunte'
    _description = 'Apunte Contable (Journal Item)'

    asiento_id = fields.Many2one('bateria.asiento', string='Asiento', ondelete='cascade')
    cuenta_id = fields.Many2one('bateria.cuenta.contable', string='Cuenta Contable', required=True)
    cliente_id = fields.Many2one('bateria.cliente', string='Cliente / Proveedor')
    nombre = fields.Char(string='Etiqueta / Descripción')
    debe = fields.Float(string='Debe', default=0.0)
    haber = fields.Float(string='Haber', default=0.0)
    fecha = fields.Date(related='asiento_id.fecha', store=True)
    diario_id = fields.Many2one(related='asiento_id.diario_id', store=True)

class BateriaLibroVentasWizard(models.TransientModel):
    _name = 'bateria.libro.ventas.wizard'
    _description = 'Asistente de Libro de Ventas'
    
    company_id = fields.Many2one('res.company', string='Compañía', required=True, default=lambda self: self.env.company)
    fecha_inicio = fields.Date(string='Desde', required=True, default=fields.Date.context_today)
    fecha_fin = fields.Date(string='Hasta', required=True, default=fields.Date.context_today)

    def action_generar_libro(self):
        ventas = self.env['bateria.orden.venta'].search([
            ('fecha_creacion', '>=', self.fecha_inicio), 
            ('fecha_creacion', '<=', self.fecha_fin), 
            ('estado', 'in', ['parcial', 'pagado']),
            ('company_id', '=', self.company_id.id)  # 👈 FILTRO POR EMPRESA
        ], order='fecha_creacion asc, id asc')
        if not ventas: 
            raise UserError("No hay ventas registradas en este rango de fechas para esta empresa.")
        return self.env.ref('bateria_reportes.action_report_libro_ventas').with_context(fecha_inicio=self.fecha_inicio.strftime('%d/%m/%Y'), fecha_fin=self.fecha_fin.strftime('%d/%m/%Y')).report_action(ventas)

class BateriaLibroComprasWizard(models.TransientModel):
    _name = 'bateria.libro.compras.wizard'
    _description = 'Asistente de Libro de Compras'
    
    company_id = fields.Many2one('res.company', string='Compañía', required=True, default=lambda self: self.env.company)
    fecha_inicio = fields.Date(string='Desde', required=True, default=fields.Date.context_today)
    fecha_fin = fields.Date(string='Hasta', required=True, default=fields.Date.context_today)

    def action_generar_libro(self):
        return self.env.ref('bateria_reportes.action_report_libro_compras').report_action(self)

class BateriaReporteFinancieroWizard(models.TransientModel):
    _name = 'bateria.financiero.wizard'
    _description = 'Asistente de Estados Financieros'
    tipo_reporte = fields.Selection([('resultados', 'Estado de Ganancias y Pérdidas (P&L)'), ('balance', 'Balance General')], string='Tipo de Reporte', required=True, default='resultados')
    fecha_inicio = fields.Date(string='Desde', default=fields.Date.context_today)
    fecha_fin = fields.Date(string='Hasta (Fecha de Corte)', required=True, default=fields.Date.context_today)

    def get_datos_resultados(self):
        datos = {'ingresos': [], 'costos': [], 'gastos': [], 'totales': {}}
        domain_base = [('asiento_id.estado', '=', 'asentado'), ('fecha', '>=', self.fecha_inicio), ('fecha', '<=', self.fecha_fin)]
        def get_saldos(tipo, multiplicador):
            cuentas = self.env['bateria.cuenta.contable'].search([('tipo', '=', tipo)])
            resultado, total = [], 0.0
            for c in cuentas:
                apuntes = self.env['bateria.apunte'].search(domain_base + [('cuenta_id', '=', c.id)])
                if apuntes:
                    saldo = sum((a.debe - a.haber) * multiplicador for a in apuntes)
                    if saldo != 0: resultado.append({'codigo': c.codigo, 'nombre': c.name, 'saldo': saldo}); total += saldo
            return sorted(resultado, key=lambda x: x['codigo'] if x['codigo'] else ''), total

        ingresos, t_ing = get_saldos('4', multiplicador=-1)
        costos, t_cos = get_saldos('5', multiplicador=1)
        gastos, t_gas = get_saldos('6', multiplicador=1)
        datos['ingresos'], datos['costos'], datos['gastos'] = ingresos, costos, gastos
        datos['totales'] = {'ingresos': t_ing, 'costos': t_cos, 'gastos': t_gas, 'utilidad_bruta': t_ing - t_cos, 'utilidad_neta': t_ing - t_cos - t_gas}
        return datos

    def get_datos_balance(self):
        datos = {'activos': [], 'pasivos': [], 'patrimonio': [], 'totales': {}}
        domain_base = [('asiento_id.estado', '=', 'asentado'), ('fecha', '<=', self.fecha_fin)]
        def get_saldos(tipo, multiplicador):
            cuentas = self.env['bateria.cuenta.contable'].search([('tipo', '=', tipo)])
            resultado, total = [], 0.0
            for c in cuentas:
                apuntes = self.env['bateria.apunte'].search(domain_base + [('cuenta_id', '=', c.id)])
                if apuntes:
                    saldo = sum((a.debe - a.haber) * multiplicador for a in apuntes)
                    if saldo != 0: resultado.append({'codigo': c.codigo, 'nombre': c.name, 'saldo': saldo}); total += saldo
            return sorted(resultado, key=lambda x: x['codigo'] if x['codigo'] else ''), total
            
        activos, t_act = get_saldos('1', multiplicador=1)
        pasivos, t_pas = get_saldos('2', multiplicador=-1)
        patrimonio, t_pat = get_saldos('3', multiplicador=-1)
        
        apuntes_util = self.env['bateria.apunte'].search(domain_base + [('cuenta_id.tipo', 'in', ['4', '5', '6'])])
        utilidad = 0.0
        for a in apuntes_util:
            if a.cuenta_id.tipo == '4': utilidad += (a.haber - a.debe)
            else: utilidad -= (a.debe - a.haber)
                
        datos['activos'], datos['pasivos'], datos['patrimonio'] = activos, pasivos, patrimonio
        datos['totales'] = {'activos': t_act, 'pasivos': t_pas, 'patrimonio': t_pat, 'utilidad': utilidad, 'pasivo_y_patrimonio': t_pas + t_pat + utilidad}
        return datos

    def action_generar_reporte(self):
        if self.tipo_reporte == 'resultados': return self.env.ref('bateria_reportes.action_report_estado_resultados').report_action(self)
        else: return self.env.ref('bateria_reportes.action_report_balance_general').report_action(self)