# Que Hai Hoxe?

Radar de eventos de Galicia con búsqueda por municipio, categoría, fecha y hora de inicio. Las fichas enlazan a la información oficial. El mapa muestra recintos con coordenadas comprobadas.

## Ver la web y el backend

- **Web en GitHub Pages.** El enlace del despliegue aparece en el entorno **github-pages** del repositorio. La web pública lee un JSON y fichas HTML generadas previamente.
- **Backend en FastAPI.** [Rutas y API](app/main.py) para servir la portada, el catálogo y las fichas mediante Jinja2 y SQLite. Las [pruebas de integración](tests/integration/test_database.py) verifican el uso de la base en modo de solo lectura. [CLI](app/cli.py) para importación y escritura local separadas.
- **Exportación pública.** [Generador](app/pages.py) en Python que reutiliza las plantillas y el frontend del proyecto. [Validación del artefacto público](scripts/audit_publication.py) y [automatización](.github/workflows/pages.yml).

## Demo local de FastAPI

En Windows, usa [Python 3.14.10 o una actualización posterior de 3.14](https://www.python.org/downloads/release/python-31410/) y PowerShell. La demostración usa eventos ficticios señalizados. Ejecuta el último comando cuando quieras abrir una escucha solo en tu PC.

~~~powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade --only-binary=:all: pip==26.3
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
$env:QHH_DEMO = '1'
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log
~~~

Abre <http://127.0.0.1:8000/> para ver la interfaz y <http://127.0.0.1:8000/api/events> para ver la respuesta de la API. Detén el servidor con Ctrl+C. Limpia el modo de demostración con Remove-Item Env:QHH_DEMO.

~~~powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pytest -q
node tests/frontend.mjs
~~~

## Catálogo público y actualización

GitHub Actions consulta la Xunta y publica el catálogo a partir de las 06:23 UTC cada día. A las 10:47, 14:47 y 20:47 UTC hay oportunidades de recuperación. En esos horarios el flujo consulta la fecha de importación del JSON público. Si acredita una publicación posterior o igual a la cita del día, termina ahí. Si falta o no se puede comprobar, vuelve a generar y auditar el catálogo. Un error de origen, generación o auditoría conserva la última publicación correcta. También puedes iniciar la actualización desde **Actions → Actualizar y publicar el radar → Run workflow**.

La edición pública parte del servicio oficial de la Xunta. La página de fuentes indica cuándo se consultó y las fichas conservan la actualización indicada por el proveedor. GitHub puede retrasar ejecuciones programadas y desactivarlas tras 60 días de inactividad de un repositorio público. La ejecución manual permite actualizar el catálogo cuando haga falta. [Programación en GitHub Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

## Créditos

Fuente de los datos: [Xunta de Galicia · Axenda de Cultura de Galicia](https://abertos.xunta.gal/catalogo/cultura-ocio-deporte/-/dataset/0045/axenda-cultura-galicia), [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). La exportación selecciona únicamente los campos de agenda, conserva la fuente, normaliza fechas y categorías y comprueba recintos. Proyecto independiente.

Mapa con teselas [CC BY 4.0 scne.es · IGN](https://www.ign.es/resources/licencia/Condiciones_licenciaUso_IGN.pdf) y [Leaflet bajo BSD-2-Clause](app/static/vendor/leaflet/LICENSE). El catálogo y la cartografía mantienen sus respectivas licencias.
