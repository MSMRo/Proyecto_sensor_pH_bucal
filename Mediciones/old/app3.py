import streamlit as st
import serial
import time
import pandas as pd
import re
from collections import deque

st.set_page_config(page_title="Monitor y Calibración de pH", layout="wide")

# --- Configuración del puerto serial ---
PORT = 'COM11'
BAUD = 115200

# Parámetros iniciales de calibración
NEUTRAL_VOLTAGE = 2.50
PH_SLOPE = 0.152

# Inicializa el puerto serial una sola vez
@st.cache_resource
def init_serial():
    try:
        ser = serial.Serial(PORT, BAUD, timeout=1)
        time.sleep(2)
        return ser
    except serial.SerialException:
        st.error(f"❌ No se pudo conectar al puerto {PORT}.")
        st.stop()
        return None

ser = init_serial()

# --- Título e interfaz principal ---
st.title("🧪 pH en tiempo real")
st.markdown("Visualización en tiempo real de los valores de voltaje y pH, con opción de calibración.")

# Contenedores para visualización
current_ph_placeholder = st.empty()
current_voltage_placeholder = st.empty()
chart_placeholder = st.empty()
serial_text = st.empty()

# --- Sidebar de calibración ---
st.sidebar.header("Calibración del Sensor de pH")
st.sidebar.markdown("Ingresa un valor de pH conocido para calibrar tu sensor.")

# Input para valor de calibración
cal_ph_value = st.sidebar.number_input(
    "Valor de pH conocido (ej. 7.0, 4.0, 10.0)",
    min_value=0.0,
    max_value=14.0,
    value=7.0,
    step=0.1,
    format="%.1f"
)

# Variables de estado para control de botones
if 'calibrate_neutral_triggered' not in st.session_state:
    st.session_state.calibrate_neutral_triggered = False
if 'calibrate_slope_triggered' not in st.session_state:
    st.session_state.calibrate_slope_triggered = False
if 'calibration_points' not in st.session_state:
    st.session_state.calibration_points = []

# Botones (modifican el estado solo una vez)
if st.sidebar.button("Calibrar Punto Neutro (pH 7.0)"):
    st.session_state.calibrate_neutral_triggered = True
if st.sidebar.button("Calibrar Pendiente (con 2 puntos)"):
    st.session_state.calibrate_slope_triggered = True

# Mostrar los parámetros actuales
st.sidebar.markdown("---")
st.sidebar.markdown("**Parámetros Actuales:**")
st.sidebar.markdown(f"**Voltaje Neutro (pH 7):** `{NEUTRAL_VOLTAGE:.3f} V`")
st.sidebar.markdown(f"**Pendiente (V/pH):** `{PH_SLOPE:.3f}`")

# Función de cálculo de pH
def calculate_ph(voltage, neutral_v, ph_slope):
    return 7 + ((neutral_v - voltage) / ph_slope)

# Funciones de calibración
def calibrate_neutral_point(measured_voltage, known_ph=7.0):
    global NEUTRAL_VOLTAGE
    NEUTRAL_VOLTAGE = measured_voltage
    st.sidebar.success(f"Punto neutro calibrado: {NEUTRAL_VOLTAGE:.3f} V")

def calibrate_slope(v1, ph1, v2, ph2):
    global PH_SLOPE, NEUTRAL_VOLTAGE
    try:
        PH_SLOPE = (v1 - v2) / (ph2 - ph1)
        NEUTRAL_VOLTAGE = v1 + (ph1 - 7) * PH_SLOPE
        st.sidebar.success(f"Pendiente: {PH_SLOPE:.3f} V/pH. Neutro: {NEUTRAL_VOLTAGE:.3f} V")
        st.session_state.calibration_points = []
    except ZeroDivisionError:
        st.sidebar.error("Error: los pH ingresados son iguales.")
    except Exception as e:
        st.sidebar.error(f"Error en calibración: {e}")

# Buffers de datos
MAX_DATA_POINTS = 100
time_data = deque(maxlen=MAX_DATA_POINTS)
voltage_data = deque(maxlen=MAX_DATA_POINTS)
ph_data = deque(maxlen=MAX_DATA_POINTS)

# Bucle de lectura
if ser:
    while True:
        if ser.in_waiting:
            try:
                line = ser.readline().decode("utf-8").strip()
                match = re.search(r"Voltaje:\s*([\d.]+)\s*V\s*\|\s*pH:\s*([\d.]+)", line)

                if match:
                    voltaje_arduino = float(match.group(1))
                    ph_calculated = calculate_ph(voltaje_arduino, NEUTRAL_VOLTAGE, PH_SLOPE)

                    current_voltage_placeholder.metric("Voltaje actual", f"{voltaje_arduino:.3f} V")
                    current_ph_placeholder.metric("Valor de pH calculado", f"{ph_calculated:.3f}")

                    # Actualizar datos
                    time_data.append(time.time())
                    voltage_data.append(voltaje_arduino)
                    ph_data.append(ph_calculated)

                    df_chart = pd.DataFrame({
                        "Tiempo": list(time_data),
                        "Voltaje (V)": list(voltage_data),
                        "pH": list(ph_data)
                    })

                    with chart_placeholder:
                        st.line_chart(df_chart, y=["Voltaje (V)", "pH"], use_container_width=True)

                    # --- Calibración ---
                    if st.session_state.calibrate_neutral_triggered:
                        calibrate_neutral_point(voltaje_arduino, cal_ph_value)
                        st.session_state.calibrate_neutral_triggered = False

                    if st.session_state.calibrate_slope_triggered:
                        if len(st.session_state.calibration_points) < 2:
                            st.session_state.calibration_points.append({
                                "voltage": voltaje_arduino,
                                "ph": cal_ph_value
                            })
                            st.sidebar.info(f"Punto #{len(st.session_state.calibration_points)} registrado: V={voltaje_arduino:.3f}, pH={cal_ph_value:.1f}")

                            if len(st.session_state.calibration_points) == 2:
                                p1, p2 = st.session_state.calibration_points
                                calibrate_slope(p1['voltage'], p1['ph'], p2['voltage'], p2['ph'])
                        else:
                            st.sidebar.warning("Ya hay 2 puntos registrados.")
                        st.session_state.calibrate_slope_triggered = False

                else:
                    serial_text.text(f"🔸 Formato inesperado: {line}")

            except UnicodeDecodeError:
                serial_text.text("🔸 Error de codificación.")
            except ValueError:
                serial_text.text(f"🔸 No se pudo convertir: {line}")
            except Exception as e:
                st.error(f"❌ Error inesperado: {e}")

        time.sleep(0.1)
