import base64
import csv
import io
from datetime import datetime
from odoo import models, fields, api
from odoo.exceptions import UserError

class ImportarCxCWizard(models.TransientModel):
    _name = 'bateria.importar.cxc.wizard'
    _description = 'Asistente para importar Cuentas por Cobrar'

    archivo = fields.Binary(string='Archivo CSV', required=True)
    nombre_archivo = fields.Char(string='Nombre del Archivo')

    def action_importar(self):
        if not self.archivo:
            raise UserError("Sube un archivo CSV primero.")

        try:
            # Leer el archivo CSV
            csv_data = base64.b64decode(self.archivo).decode('utf-8-sig')
            input_file = io.StringIO(csv_data)
            reader = csv.DictReader(input_file, delimiter=',')
        except Exception as e:
            raise UserError(f"Error al leer el archivo. Asegúrate de guardarlo como 'CSV UTF-8 (delimitado por comas)'. Detalle: {str(e)}")

        creadas = 0
        
        # Buscar almacén principal y producto genérico de deuda
        ubicacion = self.env['bateria.ubicacion'].search([], limit=1)
        producto_generico = self.env['bateria.producto'].search([('nombre', '=', 'DEUDA HISTORICA')], limit=1)
        if not producto_generico:
            producto_generico = self.env['bateria.producto'].create({
                'nombre': 'DEUDA HISTORICA',
                'requiere_serial': False
            })

        for row in reader:
            cliente_nombre = row.get('CLIENTE', '').strip()
            rif = row.get('RIF', '').strip()
            referencia = row.get('REFERENCIA', '').strip() or 'DEUDA-VIEJA'
            fecha_str = row.get('FECHA', '').strip()
            monto_str = row.get('MONTO', '0').strip()

            if not cliente_nombre or not monto_str:
                continue

            try:
                monto = float(monto_str.replace(',', '.'))
            except:
                monto = 0.0

            if monto <= 0:
                continue

            # Parsear fecha o usar la de hoy si está vacía
            try:
                fecha_hist = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            except:
                fecha_hist = fields.Date.context_today(self)

            # Buscar o crear al cliente
            cliente = self.env['bateria.cliente'].search([('rif', '=', rif)], limit=1) if rif else False
            if not cliente:
                cliente = self.env['bateria.cliente'].search([('name', 'ilike', cliente_nombre)], limit=1)
            if not cliente:
                cliente = self.env['bateria.cliente'].create({
                    'name': cliente_nombre,
                    'rif': rif or 'J-000000000'
                })

            # Crear la deuda como orden de venta histórica
            orden = self.env['bateria.orden.venta'].create({
                'cliente_id': cliente.id,
                'referencia_pedido': referencia,
                'fecha_historica': fecha_hist,
                'es_venta_historica': True,
                'condiciones_pago': 'credito',
                'moneda': 'usd',
                'ubicacion_id': ubicacion.id if ubicacion else False,
                'linea_ids': [(0, 0, {
                    'producto_id': producto_generico.id,
                    'cantidad': 1,
                    'precio_usd': monto,
                })]
            })
            
            # Confirmar la venta para asentar la deuda en la contabilidad
            orden.action_confirmar_venta_y_descargar()
            creadas += 1

        return {
            'effect': {
                'fadeout': 'slow',
                'message': f'¡Éxito! Se importaron {creadas} deudas históricas al sistema.',
                'type': 'rainbow_man',
            }
        }