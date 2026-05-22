{
    "name": "Sistema de Reportes Batería",
    "version": "1.0.0",
    "summary": "Sistema completo de gestión para empresa de baterías",
    "description": """
    MÓDULO COMPLETO PARA GESTIÓN DE EMPRESA DE BATERÍAS
    
    Características principales:
    ----------------------------
    1. Reporte Gerencial Batería
    2. Reporte Cierre Caja ($, Bs, Transferencia)
    3. Reporte Batería Reposición por Modelo
    4. Reporte Venta por Modelo
    5. Reporte Cuentas por Cobrar x Distribuidor
    6. Reporte Cuentas por Pagar
    7. Reporte Pagos Realizados
    8. Reporte Inventario Chatarra
    9. Reporte de Ventas por Promoción
    10. Reporte CASHEA
    11. Conciliación Bancaria
    """,
    "category": "Sales",
    "author": "drbattery",
    "website": "",
    "depends": ["base"],
    "data": [
        # Security
        "security/ir.model.access.csv",
        
        # Data  
        "data/secuencias.xml",
        
        # Views
        "views/menus.xml",
    ],
    "demo": [
        "demo/demo_data.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
    "license": "LGPL-3"
}