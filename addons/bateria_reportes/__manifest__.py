{
    'name': 'Gestión de Baterías - Módulos Personalizados',
    'version': '1.0',
    'summary': 'Personalización de vistas e iconos nativos mediante herencia.',
    'category': 'Tools',
    'author': 'JuanDev',
    'depends': [
        'base',
        'web',
        'stock',     # Estos modulos
        'purchase',  # Son necesarios
        'mail',      # Para adaptar
        'contacts',  # La Localizacion
        'account',   # A la empresa
        'sale'  # Lo necesitas para heredar Ventas
    ],
    'data': [
        'views/inventario_modif_view.xml',  # Aquí es donde has personalizado las vistas de picking
        'views/dashboard_view.xml' 
    ],
    'assets': {
        'web.assets_backend': [
            'bateria_reportes/static/src/dashboard.js',
            'bateria_reportes/static/src/dashboard.css',
            'bateria_reportes/static/src/dashboard.xml',
        ],
    },

    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}