/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";

class BateriaDashboard extends Component {
    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        
        // Estado reactivo de las variables
        this.state = useState({
            alertasTraslado: [],
            isVentas: false,
            isCompras: false,
            isContabilidad: false,
            isAdmin: false,
        });

        onWillStart(async () => {
            this.state.isVentas = await user.hasGroup("bateria_reportes.group_bateria_venta");
            this.state.isCompras = await user.hasGroup("bateria_reportes.group_bateria_compra");
            this.state.isContabilidad = await user.hasGroup("bateria_reportes.group_bateria_contabilidad");
            this.state.isAdmin = await user.hasGroup("bateria_reportes.group_bateria_admin");

            // Solo el administrador busca las alertas en la base de datos
            if (this.state.isAdmin) {
                await this.buscarTrasladosPendientes();
            }
        });
    }

    async buscarTrasladosPendientes() {
        const traslados = await this.orm.searchRead(
            "bateria.traslado",
            [["estado", "=", "borrador"]], 
            ["id", "name", "fecha"]
        );
        this.state.alertasTraslado = traslados;
    }

    abrirTraslado(traslado_id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "bateria.traslado",
            res_id: traslado_id,
            views: [[false, "form"]],
            target: "current"
        });
    }

    // --- ACCIONES DE NAVEGACIÓN ---
    openVentas() { this.action.doAction("sale.action_orders", { clearBreadcrumbs: true }); } // Accion para ir al modulo de ventas
    openInventario() { this.action.doAction("stock.stock_picking_type_action", { clearBreadcrumbs: true }); } // Accion para ir al modulo de inventario  
    openReportes() { this.action.doAction("spreadsheet_dashboard.menu_dashboard_management", { clearBreadcrumbs: true }); } // Accion para ir al modulo de reportes gerenciales
    openCompras() { this.action.doAction("purchase.purchase_form_action", { clearBreadcrumbs: true }); } // Accion para ir al modulo de compras
    openGastos() { this.action.doAction("hr_expense.hr_expense_actions_my_all", { clearBreadcrumbs: true }); } // Accion para ir al modulo de gastos
    
    openCatalogo() { this.action.doAction("bateria_reportes.action_bateria_producto", { clearBreadcrumbs: true }); } 
    openEmbarques() { this.action.doAction("bateria_reportes.action_bateria_embarque", { clearBreadcrumbs: true }); } // 👇 Nueva Acción
    openServicios() { this.action.doAction("bateria_reportes.action_bateria_servicio", { clearBreadcrumbs: true }); }
    openActivos() { this.action.doAction("bateria_reportes.action_bateria_activo", { clearBreadcrumbs: true }); }
    openFlota() { this.action.doAction("bateria_reportes.action_bateria_vehiculo", { clearBreadcrumbs: true }); }
    openTaller() { this.action.doAction("bateria_reportes.action_bateria_taller_articulo", { clearBreadcrumbs: true }); }
    openContabilidad() { this.action.doAction("bateria_reportes.action_bateria_auditor_bdt", { clearBreadcrumbs: true }); }
    openReparaciones() { this.action.doAction("bateria_reportes.action_bateria_reparacion", { clearBreadcrumbs: true }); }
}

BateriaDashboard.template = "bateria_reportes.Dashboard";
registry.category("actions").add("bateria_reportes.dashboard", BateriaDashboard);