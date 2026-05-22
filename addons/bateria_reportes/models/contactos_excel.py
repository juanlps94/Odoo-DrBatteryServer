from odoo import models, fields

class BateriaContactosExcel(models.Model):
    _name = 'bateria.contactos.excel'
    _description = 'Contactos importados desde Excel'

    nombre = fields.Char(string='Nombre', required=True)
    moneda_visualizacion = fields.Char(string='Moneda de visualización')
    total_adeudado = fields.Float(string='Total adeudado')

    movil = fields.Char(string='Móvil')
    telefono = fields.Char(string='Teléfono')
    email = fields.Char(string='Correo electrónico')

    comercial = fields.Char(string='Comercial')
    actividades = fields.Char(string='Actividades')

    ciudad = fields.Char(string='Ciudad')
    pais = fields.Char(string='País')
    idioma = fields.Char(string='Idioma')
    compania = fields.Char(string='Compañía')
