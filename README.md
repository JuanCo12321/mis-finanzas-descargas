# Mis Finanzas · Descargas

Aquí se publican las apps de Mis Finanzas para **Android** (`mis-finanzas.apk`) y **Windows** (`mis-finanzas-windows.zip`), en [Releases](https://github.com/JuanCo12321/mis-finanzas-descargas/releases/latest).

La web está en [mis-finanzas-online.web.app](https://mis-finanzas-online.web.app/). Las versiones nuevas se instalan encima de la anterior y la app avisa cuando hay una.

## Tasas de interés

`tasas.json` tiene la tasa promedio que cobró cada banco, financiera y cooperativa a las personas en las últimas cuatro semanas, por tipo de crédito, más la tasa de usura del mes. Sale de los datos abiertos de la Superintendencia Financiera de Colombia (formato 414). La app la usa para proponer la tasa de cada deuda.

Lo actualiza cada semana la tarea [`tasas.yml`](.github/workflows/tasas.yml) con [`tasas/tasas.py`](tasas/tasas.py).
