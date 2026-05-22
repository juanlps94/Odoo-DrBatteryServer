import requests
from bs4 import BeautifulSoup
from odoo import models, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class BCVScraper(models.AbstractModel):
    _name = 'bateria.bcv.scraper'
    _description = 'Robot Scraper de Tasas (BCV y USDT)'

    @api.model
    def actualizar_tasas_completas(self):
        mensajes_error = []
        
        # =========================================================
        # 1. ACTUALIZAR USDT (Usando la ruta 'Paralelo' que es irrompible)
        # =========================================================
        try:
            _logger.info("🤖 Conectando directamente al backend de Binance P2P...")
            url_binance = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Content-Type": "application/json"
            }
            # tradeType "BUY" busca el precio al que los comerciantes VENDEN el USDT (El Paralelo Real)
            payload = {
                "page": 1, "rows": 2, "payTypes": [], "asset": "USDT",
                "tradeType": "BUY", "fiat": "VES", "publisherType": None
            }
            
            respuesta_usdt = requests.post(url_binance, headers=headers, json=payload, timeout=10)
            
            if respuesta_usdt.status_code == 200:
                datos = respuesta_usdt.json()
                if datos.get('data'):
                    # Extraemos el precio exacto del primer comerciante en la lista
                    tasa_usdt = float(datos['data'][0]['adv']['price'])
                    self.env['ir.config_parameter'].sudo().set_param('bateria.tasa_usdt', str(tasa_usdt))
                    _logger.info(f"✅ Tasa Binance P2P Directa Actualizada: {tasa_usdt}")
                else:
                    mensajes_error.append("Binance respondió, pero no hay comerciantes activos ahora mismo.")
            else:
                mensajes_error.append(f"Bloqueo de Binance. Código: {respuesta_usdt.status_code}")
                
        except Exception as e:
            mensajes_error.append(f"Falla de conexión a Binance: {str(e)}")

        # =========================================================
        # 2. ACTUALIZAR BCV
        # =========================================================
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            url = 'https://www.bcv.org.ve/'
            
            _logger.info("🤖 Conectando al BCV...")
            response = requests.get(url, headers=headers, verify=False, timeout=15)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # TASA DÓLAR
                dolar_div = soup.find('div', id='dolar')
                if dolar_div:
                    precio_str = dolar_div.find('div', class_='centrado').text.strip()
                    precio_usd = float(precio_str.replace(',', '.'))
                    self.env['ir.config_parameter'].sudo().set_param('bateria.tasa_bcv_usd', str(precio_usd))
                
                # TASA EURO
                euro_div = soup.find('div', id='euro')
                if euro_div:
                    precio_str = euro_div.find('div', class_='centrado').text.strip()
                    precio_eur = float(precio_str.replace(',', '.'))
                    self.env['ir.config_parameter'].sudo().set_param('bateria.tasa_bcv_eur', str(precio_eur))
            else:
                mensajes_error.append(f"El BCV no responde. Código: {response.status_code}")
                    
        except Exception as e:
            mensajes_error.append(f"Falla de conexión al BCV: {str(e)}")

        # =========================================================
        # REPORTE DE ERRORES EN PANTALLA
        # =========================================================
        if mensajes_error:
            error_texto = "\n\n".join(mensajes_error)
            raise UserError(f"⚠️ Hubo problemas al actualizar las tasas:\n\n{error_texto}\n\nRevisa la conexión a internet o intenta en unos minutos.")
        
        return True