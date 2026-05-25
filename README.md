# Dr Battery

> Modulo de reportes de bateria, la rama de desarrollo se llamada bateria_jyDev

## 🚀 Características
*   Integración con sistemas Odoo.
*   Automatización de procesos.

## 🛠️ Tecnologías Utilizadas
*   **Lenguaje:** Python / JavaScript / etc.
*   **Frameworks:** 
*   **Base de Datos:** PostgreSQL / MySQL.

## 📦 Instalación

Para replicar este entorno localmente, sigue estos pasos:

1. **Clonar el repositorio:**
   ```bash
   git clone [https://github.com/pruebaodoo145-max/Odoo-DrBatteryServer]
   ```

2. **Para ejecutar Odoo:**

Primero se debe ejecutar el entorno virtual.
   ```bash
   source venv/bin/activate
   ```

Luego se ejecuta Odoo:
   - Para produccion: 
   
   En odoo-pro/odoo
   
   ./start_odoo_prod.sh    Esto carga la configuración de odoo.conf para producción

   Opcionalmente:

   ```bash
   ./odoo-bin --addons-path=addons --http-interface 0.0.0.0 --http-port 8069 -d bateria_dev
   ```

   - Para desarrollo 
   En odoo-dev/odoo
   ./start_odoo_dev.sh    Esto carga la configuración de odoo.conf para desarrollo
   
   Opcionalmente:

   ```bash
   ./odoo-bin --addons-path=addons --http-interface 0.0.0.0 --http-port 8070 -d bateria_dev
   ```
