{
    'name': 'Gestión de Baterías - Módulos Personalizados',
    'version': '1.0',
    'summary': 'Personalización de vistas e iconos nativos mediante herencia.',
    'category': 'Tools',
    'author': 'JuanDev',
    'depends': [
        'base',
        'sale',      # Lo necesitas para heredar Ventas
        'purchase',  # Lo necesitas para heredar Compras
        'stock',     # Lo necesitas para heredar Inventario (si aplica)
    ],
    'data': [
        'views/inventario_modif_view.xml',  # Aquí es donde has personalizado las vistas de picking
        # Aquí iremos agregando tus archivos XML de herencia más adelante
    ],
    'assets': {
        'web.assets_backend': [
            'bateria_reportes/static/src/scss/custom_style.scss',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}