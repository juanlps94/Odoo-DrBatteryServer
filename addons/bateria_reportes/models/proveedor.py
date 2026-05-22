from odoo import models, fields

class BateriaProveedor(models.Model):
    _name = 'bateria.proveedor'
    _description = 'Registro de Proveedores'
    _rec_name = 'nombre_empresa'

    nombre_empresa = fields.Char(string='Nombre Empresa', required=True)
    rif = fields.Char(string='RIF', required=True)
    direccion = fields.Text(string='Dirección')
    telefono = fields.Char(string='Teléfono')
    correo = fields.Char(string='Correo Electrónico')
    categoria = fields.Char(string='Categoría')
    sub_categoria = fields.Char(string='Sub-Categoría')
    articulos = fields.Char(string='Artículos')