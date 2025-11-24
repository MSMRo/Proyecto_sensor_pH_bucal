# Proyecto Sensor pH Bucal

Breve descripción
------------------

Sistema integrado (hardware + firmware + software) para la medición y registro de valores de pH bucal. El proyecto incluye el diseño de la carcasa y el electrodo, el firmware para microcontroladores (p. ej. XIAO/Arduino), herramientas para generar y procesar lecturas ADC, y una interfaz de usuario en Streamlit para visualizar y guardar mediciones.

Características principales
- **Medición**: adquisición de señal analógica desde un electrodo de pH y conversión a valores digitales.
- **Firmware**: ejemplo de sketch para XIAO/Arduino con transmisión serial / BLE.
- **Procesamiento**: scripts y notebooks para convertir voltajes a pH, visualizar series temporales y exportar a CSV.
- **Interfaz**: aplicación Streamlit (`software/UI_streamlit/main.py`) para lectura en tiempo real y visualización.

Estructura del repositorio
- **`Hardware/`**: archivos de diseño de la carcasa y del electrodo.
- **`Mediciones/`**: código y pruebas antiguas de adquisición.
- **`software/firmware/`**: sketches y utilidades para el microcontrolador (incluye `xiao_ble` y generador de texto ADC).
- **`software/UI_streamlit/`**: interfaz Streamlit y recursos gráficos.
- **`software/*.ipynb`**: notebooks para análisis y plots.

Cómo comenzar (rápido)
----------------------

- Instalar dependencias (Python):

```
pip install streamlit pyserial pandas matplotlib
```

- Ejecutar la interfaz Streamlit (desde la carpeta `software/UI_streamlit`):

```
cd software\UI_streamlit
streamlit run main.py
```

- Para revisar el firmware: abrir `software/firmware/xiao_ble/xiao_ble.ino` o `software/firmware/serial/gen_text_adc_v1/gen_text_adc_v1.ino` en el IDE de Arduino y cargar en la placa correspondiente.

Notas y gestión de datos
- Los datos de medición pueden guardarse como CSV usando los notebooks o la propia UI.
- Los notebooks en `software/` contienen ejemplos de calibración y visualización.

Contacto
- Autor: MSMRo (repositorio: `Proyecto_sensor_pH_bucal`)
