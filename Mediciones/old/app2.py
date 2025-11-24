import streamlit as st
import serial
import time
import pandas as pd
import re
import threading

st.set_page_config(page_title="Calibración Sensor pH", layout="wide")

PORT = 'COM11'
BAUD = 115200

@st.cache_resource
def init_serial():
    try:
        ser = serial.Serial(PORT, BAUD, timeout=1)
        time.sleep(2)
        return ser
    except:
        st.error("❌ Error conectando al puerto serial.")
        return None

ser = init_serial()

st.title("🧪 Calibración y Lectura de Sensor de pH")

# Variables globales
cal_data = {
    "ph7_voltage": None,
    "ph4_voltage": None,
    "ph10_voltage": None,
    "slope": None
}

data = []
serial_text = st.empty()
chart = st.line_chart()

# Contenedor para datos en tiempo real
with st.expander("📡 Datos en tiempo real del sensor", expanded=True):
    volt_display = st.empty()
    ph_display = st.empty()

def serial_reader():
    global data
    while True:
        if ser and ser.in_waiting:
            try:
                line = ser.readline().decode("utf-8").strip()
                serial_text.text(f"🔸 {line}")

                match = re.search(r"Voltaje: ([\d.]+).*pH: ([\d.]+)", line)
                if match:
                    volt = float(match.group(1))
                    raw_ph = float(match.group(2))

                    # Mostrar valores actuales siempre
                    volt_display.metric("🔌 Voltaje", f"{volt:.3f} V")
                    ph_display.metric("🧪 pH leído (Arduino)", f"{raw_ph:.2f}")

                    # Calcular nuevo pH si calibrado
                    if cal_data["slope"]:
                        calc_ph = 7 + (cal_data["ph7_voltage"] - volt) / cal_data["slope"]
                    else:
                        calc_ph = raw_ph

                    data.append({"Voltaje (V)": volt, "pH": calc_ph})
                    if len(data) > 100:
                        data = data[-100:]

                    df = pd.DataFrame(data)
                    chart.line_chart(df)

            except Exception as e:
                st.error(f"Error leyendo serial: {e}")

# Iniciar lectura en hilo separado
if ser:
    thread = threading.Thread(target=serial_reader, daemon=True)
    thread.start()

# Panel de calibración
with st.expander("⚙️ Calibración del sensor"):
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("📍 Establecer pH 7 (2.5 V)"):
            cal_data["ph7_voltage"] = 2.5
            st.success("✔️ Referencia pH 7 establecida a 2.5 V")

    with col2:
        ph4_real = st.number_input("Valor real del buffer bajo (ej. 4)", value=4.0)
        if st.button("📍 Medir voltaje en buffer bajo"):
            if ser and ser.in_waiting:
                line = ser.readline().decode("utf-8").strip()
                match = re.search(r"Voltaje: ([\d.]+)", line)
                if match:
                    cal_data["ph4_voltage"] = float(match.group(1))
                    st.success(f"✔️ Voltaje para pH {ph4_real}: {cal_data['ph4_voltage']} V")

    with col3:
        ph10_real = st.number_input("Valor real del buffer alto (ej. 10)", value=10.0)
        if st.button("📍 Medir voltaje en buffer alto"):
            if ser and ser.in_waiting:
                line = ser.readline().decode("utf-8").strip()
                match = re.search(r"Voltaje: ([\d.]+)", line)
                if match:
                    cal_data["ph10_voltage"] = float(match.group(1))
                    st.success(f"✔️ Voltaje para pH {ph10_real}: {cal_data['ph10_voltage']} V")

    # Calcular pendiente
    if cal_data["ph4_voltage"] and cal_data["ph10_voltage"]:
        m1 = (7 - ph4_real) / (cal_data["ph7_voltage"] - cal_data["ph4_voltage"])
        m2 = (ph10_real - 7) / (cal_data["ph10_voltage"] - cal_data["ph7_voltage"])
        cal_data["slope"] = round((m1 + m2) / 2, 4)
        st.success(f"✅ Pendiente calibrada: {cal_data['slope']}")

