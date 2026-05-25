1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/pruebaodoo145-max/Odoo-DrBatteryServer
   ```

2. **Para ejecutar Odoo:**

Primero se debe ejecutar el entorno virtual.
   ```bash
   source venv/bin/activate
   ```

Luego se ejecuta Odoo:
   - Para produccion: 
   ```bash
   ./odoo-bin --addons-path=addons,./dr_battery --xmlrpc-interface 0.0.0.0 --xmlrpc-port 8069 -d odoo_dev -u bateria_reportes
   ```

   - Para desarrollo 
   ```bash
   ./odoo-bin --addons-path=addons,./dr_battery --xmlrpc-interface 0.0.0.0 --xmlrpc-port 8070 -d odoo_dev -u bateria_reportes

   ```
