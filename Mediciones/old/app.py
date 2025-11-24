import streamlit as st
import serial
import time
import pandas as pd
import re

# Configuración del puerto serial
PORT = 'COM11'  # ¡Cambia esto según tu sistema!
BAUD = 115200  # Igual al que usas en Serial.begin()

# Inicializa el puerto serial
@st.cache_resource
def init_serial():
    try:
        ser = serial.Serial(PORT, BAUD, timeout=1)
        time.sleep(2)
        return ser
    except:
        st.error(f"❌ No se pudo conectar al puerto {PORT}. Verifica el puerto, cable o drivers.")
        return None

ser = init_serial()

st.title("🧪 Monitor de Sensor de pH en Tiempo Real")
st.markdown("Visualización en tiempo real de los valores de voltaje y pH enviados por el microcontrolador.")

# Espacios para texto y gráfico
serial_text = st.empty()
chart = st.line_chart()
data = []

# Bucle principal
if ser:
    while True:
        if ser.in_waiting:
            try:
                line = ser.readline().decode("utf-8").strip()
                serial_text.text(f"🔸 {line}")

                # Usamos regex para extraer voltaje y pH
                match = re.search(r"Voltaje: ([\d.]+).*pH: ([\d.]+)", line)
                if match:
                    voltaje = float(match.group(1))
                    ph = float(match.group(2))
                    data.append({"Voltaje (V)": voltaje, "pH": ph})

                    # Mantener solo los últimos 100 puntos
                    if len(data) > 100:
                        data = data[-100:]

                    df = pd.DataFrame(data)
                    chart.line_chart(df)
            except Exception as e:
                st.error(f"Error leyendo datos: {e}")
