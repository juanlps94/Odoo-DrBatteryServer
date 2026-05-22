{
    'name': 'Reportes Gerenciales Batería',
    'version': '1.0',
    'category': 'Accounting',
    'summary': 'Reportes gerenciales para empresa de baterías',
    'author': 'Tu Empresa',
    'depends': [
        'base',
        'account',
        'web',  # Obligatorio para widgets monetarios y vistas modernas
    ],
    
    # LO COMENTAMOS TEMPORALMENTE PARA CURAR ODOO
    # Cuando confirmes que Odoo revivió, le quitaremos los #
    'assets': {
         'web.assets_backend': [
             'bateria_reportes/static/src/dashboard.js',
             'bateria_reportes/static/src/dashboard.css',
             'bateria_reportes/static/src/dashboard.xml',
         ],
    },

    'data': [
        'security/security.xml',
        'security/bateria_security.xml',
        'security/ir.model.access.csv',
        'wizard/importar_cxc_wizard_view.xml',
        'data/proveedores_data.xml', 
        'data/cron_bcv.xml',
        'data/secuencias.xml',
        'data/datos_contables.xml',
        # 2. Cargamos los menús al FINAL, ahora que todas las acciones ya existen
        'reports/reporte_factura.xml',
        'reports/reporte_gastos_view.xml',
        'reports/reporte_servicio_view.xml',
        'reports/reporte_compra_view.xml',
        'views/menus.xml',
        'views/cuenta_pagar_view.xml',
        # 1. Cargamos las vistas que contienen las acciones (actions)
        'views/dashboard_action.xml',
        'views/producto_view.xml',
        'views/inventario_view.xml',
        'views/pago_view.xml',
        'views/orden_venta_view.xml', # Aquí está action_bateria_orden_venta
        'views/compras_view.xml',  
        'views/cierre_caja_view.xml',
        'views/analisis_ventas_view.xml',
        'views/tabla_dinamica_ventas_view.xml',
        'views/contactos_excel_view.xml',
        'views/activos_view.xml',
        'views/flota_view.xml',
        'views/taller_view.xml',
        'views/contabilidad_view.xml',
        'views/recepcion_view.xml',
        'views/reparacion_view.xml',
        'views/wizard_importar_ventas_view.xml',
        'views/gastos_view.xml',
        'views/servicios_view.xml',
        'views/reparacion_carros_view.xml',
        'views/embarque_view.xml',
        

        # 3. Reportes
        'reports/libro_mayor_report.xml',
        'reports/analisis_ventas_report.xml',
        'reports/analisis_ventas_template.xml',
        'reports/tabla_dinamica_ventas_template.xml',
        'reports/tabla_dinamica_ventas_report.xml',
        'reports/contactos_excel_report.xml',
        'reports/contactos_excel_template.xml',
        'reports/orden_venta_template.xml',
        'reports/orden_venta_report.xml', 
        'reports/reporte_cuentas_pagar.xml',
        'reports/reporte_flota.xml',
        'reports/reporte_taller.xml',

        
         # <-- IMPORTANTE: CARGA LOS DATOS
           # <-- IMPORTANTE: LAS VISTAS NUEVAS
        # 5. Menús SIEMPRE al final para que todas las acciones existan
        
    ],
    'installable': True,
    'application': True, # Para que aparezca fácil en el listado de apps
}