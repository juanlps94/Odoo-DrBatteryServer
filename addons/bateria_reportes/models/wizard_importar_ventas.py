from odoo import models, fields, api
import base64
import io
import csv
from odoo.exceptions import UserError
import re
from datetime import datetime, time

class BateriaImportarVentasWizard(models.TransientModel):
    _name = 'bateria.importar.ventas.wizard'
    _description = 'Importador Masivo de Ventas Historicas'

    cliente_id = fields.Many2one('bateria.cliente', string='Cliente de Respaldo')
    fecha_venta = fields.Date(string='Fecha Real de la Venta', required=True, default='2025-12-09')
    archivo_csv = fields.Binary(string='Archivo Excel (.xlsx) o CSV', required=True)
    nombre_archivo = fields.Char(string='Nombre del Archivo')
    
    def action_importar(self):
        if not self.archivo_csv:
            raise UserError("Debes subir un archivo.")
            
        nombre_arch = self.nombre_archivo.lower() if self.nombre_archivo else ''
        file_content = base64.b64decode(self.archivo_csv)
        
        # 👇 CORRECCIÓN DE ZONA HORARIA: Forzamos que sea a las 12:00 del mediodía para que no se atrase un día 👇
        fecha_dt = datetime.combine(self.fecha_venta, time(12, 0, 0))

        ventas_por_cliente = {}
        
        # 1. LECTURA DEL EXCEL POR PESTAÑAS
        if nombre_arch.endswith('.xlsx') or nombre_arch.endswith('.xls'):
            try:
                import openpyxl
            except ImportError:
                raise UserError("Tu servidor no tiene instalada la librería 'openpyxl'. Contacta a soporte.")
                
            wb = openpyxl.load_workbook(filename=io.BytesIO(file_content), data_only=True)
            for sheet_name in wb.sheetnames:
                sheet = wb[sheet_name]
                
                nombre_limpio = sheet_name.strip()
                match = re.search(r'^([A-Za-z\s\.]+)', nombre_limpio)
                if match:
                    nombre_limpio = match.group(1).strip()
                
                cliente_db = self.env['bateria.cliente'].search([('name', 'ilike', nombre_limpio)], limit=1)
                if not cliente_db:
                    cliente_db = self.env['bateria.cliente'].create({
                        'name': nombre_limpio,
                        'rif': 'Por Actualizar'
                    })
                
                matriz = []
                for row in sheet.iter_rows(values_only=True):
                    matriz.append(list(row))
                    
                self._procesar_matriz(matriz, cliente_db, ventas_por_cliente)
                
        # 2. SI ES UN SOLO ARCHIVO CSV
        elif nombre_arch.endswith('.csv'):
            if not self.cliente_id:
                raise UserError("Para archivos CSV, debes elegir un Cliente de Respaldo.")
            try:
                texto = file_content.decode('utf-8-sig')
            except:
                texto = file_content.decode('latin-1')
            reader = csv.reader(io.StringIO(texto))
            matriz = list(reader)
            self._procesar_matriz(matriz, self.cliente_id, ventas_por_cliente)
            
        else:
            raise UserError("Formato de archivo no soportado. Sube un archivo .xlsx o .csv")
            
        if not ventas_por_cliente:
            raise UserError("No se encontraron baterías ni modelos válidos en el archivo.")

        # 3. CREACIÓN FORZADA (MODO ADMINISTRADOR)
        racksito = self.env['bateria.ubicacion'].search([('nombre_completo', 'ilike', 'racksito')], limit=1)
        almacen_gral = self.env['bateria.ubicacion'].search([], limit=1)
        ubicacion_final = racksito.id if racksito else (almacen_gral.id if almacen_gral else False)
        
        total_baterias = 0
        ordenes_creadas = 0
        inventory_model = self.env['bateria.inventario']
        
        for cliente, seriales_por_producto in ventas_por_cliente.items():
            lineas_venta = []
            
            for prod, seriales_lista in seriales_por_producto.items():
                seriales_records = self.env['bateria.serial']
                
                for sn in seriales_lista:
                    sn_record = self.env['bateria.serial'].search([('nombre', '=', sn)], limit=1)
                    if not sn_record:
                        # Si no existe, lo crea obligatoriamente en el racksito
                        sn_record = self.env['bateria.serial'].create({
                            'nombre': sn,
                            'producto_id': prod.id,
                            'estado': 'disponible',
                            'ubicacion_id': ubicacion_final,
                            'fecha_ingreso': self.fecha_venta
                        })
                    else:
                        # Si existe en otro lado, lo mueve a la fuerza
                        sn_record.write({
                            'fecha_ingreso': self.fecha_venta,
                            'estado': 'disponible',
                            'ubicacion_id': ubicacion_final
                        })
                    seriales_records += sn_record
                    
                lineas_venta.append((0, 0, {
                    'producto_id': prod.id,
                    'descripcion': prod.nombre,
                    'cantidad': len(seriales_lista),
                    'serial_ids': [(6, 0, seriales_records.ids)],
                    'precio_usd': prod.precio_base_usd,
                    'saltar_regla_antiguedad': True 
                }))
                total_baterias += len(seriales_lista)
                
            if lineas_venta:
                # 👇 CREA LA FACTURA CON LA FECHA EXACTA (fecha_dt) 👇
                nueva_orden = self.env['bateria.orden.venta'].create({
                    'cliente_id': cliente.id,
                    'fecha_creacion': fecha_dt,
                    'fecha_despacho_real': self.fecha_venta,
                    'ubicacion_id': ubicacion_final,
                    'compania_origen': 'don_juan',
                    'condiciones_pago': 'credito',
                    'estado': 'parcial', # La deja por cobrar pero validada
                    'despachado': True,  # Salta el proceso de despacho visual
                    'linea_ids': lineas_venta,
                })
                
                # 👇 FUERZA LA SALIDA DE INVENTARIO EXACTAMENTE ESE DÍA 👇
                for prod, seriales_lista in seriales_por_producto.items():
                    # Descargo de Inventario Físico
                    inventory_model.create({
                        'fecha': fecha_dt,
                        'tipo_movimiento': 'salida',
                        'producto_id': prod.id,
                        'cantidad': len(seriales_lista),
                        'orden_venta_id': nueva_orden.id,
                        'ubicacion_id': ubicacion_final,
                        'nota': f"Venta Histórica Ref: {nueva_orden.referencia_pedido}"
                    })
                    
                    # Cambio de estado de Seriales y sello de garantía
                    for sn in seriales_lista:
                        sn_record = self.env['bateria.serial'].search([('nombre', '=', sn)], limit=1)
                        if sn_record:
                            sn_record.write({
                                'fecha_ingreso': self.fecha_venta,
                                'estado': 'vendido',
                                'orden_venta_id': nueva_orden.id
                            })
                ordenes_creadas += 1
                
        return {
            'effect': {
                'fadeout': 'slow',
                'message': f'¡Importación Exacta! Se despacharon {total_baterias} baterías con fecha asegurada en el {self.fecha_venta}.',
                'type': 'rainbow_man',
            }
        }

    def _procesar_matriz(self, matriz, cliente, ventas_por_cliente):
        header_idx = -1
        modelos_clave = ['22MR', '65-1000', '24M', '4D', '31H', '43M', '36MR', '45MR', '22M', '34M']
        
        for i, fila in enumerate(matriz):
            fila_strs = [str(x).upper() for x in fila if x]
            if any(modelo in f for f in fila_strs for modelo in modelos_clave):
                header_idx = i
                break
                
        if header_idx == -1:
            return
            
        headers = [str(h).strip() if h else '' for h in matriz[header_idx]]
        producto_por_columna = {}
        for idx, h in enumerate(headers):
            if not h: continue
            prod = self.env['bateria.producto'].search([('nombre', '=ilike', h)], limit=1)
            if not prod:
                prod = self.env['bateria.producto'].search([('nombre', 'ilike', h)], limit=1)
            if prod:
                producto_por_columna[idx] = prod
                
        if cliente not in ventas_por_cliente:
            ventas_por_cliente[cliente] = {}
            
        for fila in matriz[header_idx+1:]:
            for idx, val in enumerate(fila):
                if val is None: continue
                val_str = str(val).strip()
                if not val_str: continue
                if len(val_str) > 5 and 'DEPOSITO' not in val_str.upper():
                    if idx in producto_por_columna:
                        prod = producto_por_columna[idx]
                        if prod not in ventas_por_cliente[cliente]:
                            ventas_por_cliente[cliente][prod] = []
                        ventas_por_cliente[cliente][prod].append(val_str)