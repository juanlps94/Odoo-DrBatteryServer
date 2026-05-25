# Dr Battery

## 🚀 Características
*   Integración con sistemas Odoo.
*   Automatización de procesos.

## 🛠️ Tecnologías Utilizadas
*   **Lenguaje:** Python / JavaScript / etc.
*   **Frameworks:** 
*   **Base de Datos:** PostgreSQL / MySQL.
*   **Proxy inverso:** NGINX
   

# Sistema de Despliegue de Odoo 19 (Dev & Prod) con Nginx y Docker

Este repositorio contiene la arquitectura y configuración necesarias para desplegar instancias de **Odoo v19** en entornos de **Desarrollo (Dev)** y **Producción (Prod)** utilizando Docker Containers, Volúmenes Nombrados para persistencia, y Nginx como Proxy Inverso nativo en un servidor Debian.

---

## 🏗️ Arquitectura del Sistema

El flujo de tráfico está diseñado para evitar colisiones de puertos en modo `network_mode: "host"` y garantizar estabilidad en las sesiones web y WebSockets:

* **Entorno de Producción:**
    * **Nginx (Entrada pública):** Puerto `80` (HTTP) -> Redirige internamente al puerto `8069`.
    * **Odoo Core:** Puerto `8069`.
    * **Odoo Chat/WebSockets:** Puerto `8072` (Activado automáticamente con `workers > 0`).
* **Entorno de Desarrollo:**
    * **Nginx (Entrada pública):** Puerto `8080` -> Redirige internamente al puerto `8070`.
    * **Odoo Core / WebSockets:** Puerto `8070` (`workers = 0` para habilitar *autoreload* en caliente).

---

## 📁 Estructura del Proyecto (DEV)
 
```bash 
└── odoo-dev/
    ├── docker-compose.dev.yml
    ├── iniciar_dev.sh
    ├── detener_dev.sh
    ├── reiniciar_dev.sh
    └── dev/ 
        ├── data/
        │   ├── addons 
        │   ├── filestore
        │   └── sessions
        ├── config/
        │   └── odoo.conf
        └── addons/
```


🛠️ Requisitos Previos

Antes de comenzar, asegúrate de tener instalado lo siguiente en tu servidor Debian:
Docker & Docker Compose v2
Nginx instalado de forma nativa (sudo apt install nginx -y) (Opcional si estas en tu propio equipo de forma local)
NordVPN (Opcional, si se utiliza Meshnet para acceso remoto)

🚀 Instrucciones de Instalación   y Despliegue

Paso 1: Configurar los Archivos odoo.conf
```Ini, TOML
[options]
http_port = 8070
proxy_mode = FALSE   # True si se esta trabajando desde el servidor
workers = 0
addons_path = /mnt/extra-addons
limit_time_cpu = 600
limit_time_real = 1200
```


Paso 2: Configurar Docker Compose
Se implementan Volúmenes Nombrados para evitar errores de permisos de Linux en la base de datos y filestore.
A continuación se muestra el archvio docker-compose.prod.yml. 
```yml
 services:
  odoo-dev:
    image: odoo:19.0
    container_name: odoo_19_desarrollo
    user: "1000:1000"
    network_mode: "host"
    volumes:
      - ./addons:/mnt/extra-addons
      - ./config/odoo.conf:/etc/odoo/odoo.conf
      - ./data:/var/lib/odoo
    command: odoo --dev=all
```
Paso 3: Permisos

```bash
# Agregamos nuestro usuario al grupo de docker
sudo usermod -aG docker $USER  
newgrp docker

# Nos aseuramos que el usurio odoo_dev_user exista o bien lo creamos
sudo -u postgres psql - CREATE User odoo_dev_user WITH PASSWORD 'Contraseña' CREEATE DATABASE;
sudo -u postgres psql - CREATE DATABASE odoo_dev OWNER odoo_dev_usr;

Paso 3: Configurar Nginx (Proxy Inverso)
Crea el archivo de configuración para Producción y desarrollo :

```bash
  sudo nano /etc/nginx/sites-available/odoo-prod
```

Añade el siguiente bloque de configuración:
```Nginx
upstream odoo_prod {
    server 127.0.0.1:8069;
}
upstream odoo_prod_chat {
    server 127.0.0.1:8072;
}

server {
    listen 80;
    server_name _;

    client_max_body_size 100M;

    access_log /var/log/nginx/odoo_prod_access.log;
    error_log /var/log/nginx/odoo_prod_error.log;

    location /websocket {
        proxy_pass http://odoo_prod_chat;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-Host $http_host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location / {
        proxy_pass http://odoo_prod;
        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-Host $http_host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 720s;
        proxy_connect_timeout 720s;
        proxy_send_timeout 720s;
    }
}
```

Crea el archivo de configuración para Desarrollo:

```bash
sudo nano /etc/nginx/sites-available/odoo-dev
```

Añade la configuración para el puerto 8080:
```Nginx
upstream odoo_dev {
    server 127.0.0.1:8070;
}

server {
    listen 8080;
    server_name _;

    client_max_body_size 100M;

    access_log /var/log/nginx/odoo_dev_access.log;
    error_log /var/log/nginx/odoo_dev_error.log;

    location / {
        proxy_pass http://odoo_dev;
        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-Host $http_host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 720s;
        proxy_connect_timeout 720s;
        proxy_send_timeout 720s;
    }
}
```

Habilita los sitios y reinicia Nginx:
```bash
sudo rm /etc/nginx/sites-enabled/default
sudo ln -s /etc/nginx/sites-available/odoo-prod /etc/nginx/sites-enabled/
sudo ln -s /etc/nginx/sites-available/odoo-dev /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

Paso 4: Ajustes de Red y Cortafuegos (NordVPN / UFW)
Si se utiliza NordVPN en el servidor, el firewall interno puede bloquear el tráfico Wi-Fi local o los puertos de Nginx. Ejecuta lo siguiente para garantizar el acceso:

```bash
# Desactivar el descubrimiento automático si causa colisiones
nordvpn set lan-discovery disable

# Añadir la subred local y los puertos de entrada públicos a la lista blanca
nordvpn whitelist add subnet 192.168.10.0/24
nordvpn whitelist add port 80
nordvpn whitelist add port 8080
```

🛡️ Solución de Problemas Frecuentes (Troubleshooting)
1. Error 500 / 502: PermissionError: [Errno 13] Permission denied: '/var/lib/odoo/sessions'
Este error ocurre cuando Docker inicializa un Volumen Nombrado asignando la propiedad al usuario root, impidiendo que el usuario interno de Odoo (UID 1000) escriba las sesiones.
Solución quirúrgica permanente:
Busca el directorio real del volumen en el sistema anfitrión Debian y cámbiale las propiedades por la fuerza:

```bash
# 1. Encontrar la ruta del volumen nombrado
docker inspect odoo_19_produccion | grep "Source.*volumes"

# 2. Aplicar permisos de forma recursiva a la ruta obtenida
sudo chown -R 1000:1000 /var/lib/docker/volumes/TU_VOLUMEN_DATA/_data
sudo chmod -R 775 /var/lib/docker/volumes/TU_VOLUMEN_DATA/_data

# 3. Reiniciar el contenedor afectado
docker restart odoo_19_produccion
```


2. Estilos Desarmados / CSS no carga en Acceso Remoto
Si la interfaz web carga como texto plano sin formato (HTML crudo) al ingresar mediante una IP remota de NordVPN o dominio alternativo:
Verifica las Cabeceras de Nginx: Asegúrate de usar proxy_set_header Host $http_host; en lugar de $host para evitar que se pierdan los números de puerto en la redirección.
Regenerar los Assets de Odoo: Accede temporalmente mediante la URL con modo de depuración de recursos activado:
Plaintext
http://tu-ip-o-servidor/web?debug=assets

Una vez dentro, haz clic en el icono del Bicho (Bug) en la barra superior derecha y selecciona "Regenerate Assets Bundles" (Regenerar paquetes de recursos). Esto forzará al sistema a reconstruir la caché CSS corrupta.
3. Error no configuration file provided: not found
Asegúrate de pasar la bandera -f si tu archivo de Docker Compose no se llama exactamente docker-compose.yml:

```Bash
docker compose -f docker-compose.dev.yml up -d
```
