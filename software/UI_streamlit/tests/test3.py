# test2.py
# ------------------------------------------------------------
# Monitor de pH y Voltaje (Arduino → Streamlit) con:
# - Ventana deslizante configurable (N muestras visibles)
# - Placeholders para NO apilar gráficos
# - Opción de Simulador o Serial (Arduino)
# - Cálculo de pH por calibración de 2 puntos y Nernst
# - API moderna: st.rerun() y width='stretch'
# ------------------------------------------------------------

import time
import re
import math
from collections import deque
from dataclasses import dataclass
from typing import Optional

import pandas as pd
import streamlit as st

# Intentar pyserial (opcional)
try:
    import serial
    from serial import SerialException
except Exception:
    serial = None
    SerialException = Exception

# ---------------------------
# Configuración de página
# ---------------------------
st.set_page_config(page_title="Monitor de pH y Voltaje", layout="wide")

# ---------------------------
# Constantes y helpers
# ---------------------------
R = 8.31446261815324       # J/(mol·K)
F = 96485.33212            # C/mol
LN10 = math.log(10.0)

def nernst_slope_volt_per_pH(temp_c: float) -> float:
    """Pendiente Nernst (V/pH) = (R*T/F)*ln(10). A 25°C ≈ 0.05916 V/pH."""
    T = temp_c + 273.15
    return (R * T / F) * LN10

def ph_two_point(volts: float, pH1: float, V1: float, pH2: float, V2: float) -> float:
    """Calibración lineal por dos puntos: pH = a*V + b."""
    if abs(V2 - V1) < 1e-12:
        return float("nan")
    a = (pH2 - pH1) / (V2 - V1)
    b = pH1 - a * V1
    return a * volts + b

def ph_nernst(volts: float, E0: float, temp_c: float, sign: int = -1) -> float:
    """
    Modelo Nernst simplificado: pH = 7 + sign*(E - E0)/S,
    donde S = pendiente Nernst (V/pH) y E0 es el potencial a pH 7.
    sign=-1 para electrodos típicos donde el voltaje decrece con pH creciente.
    """
    S = nernst_slope_volt_per_pH(temp_c)
    if S <= 0:
        return float("nan")
    return 7.0 + sign * (volts - E0) / S

def parse_voltage_from_line(line: str) -> Optional[float]:
    """
    Acepta formatos comunes desde Arduino:
      - "V=2.9734"
      - "2.9734"
      - "V,2.9734,pH,7.01" (toma el primer float)
      - JSON-like: {"V":2.97,...} (extrae primer número)
    """
    # Primero intenta V=... explícito
    m = re.search(r"[Vv]\s*[:=]\s*([+-]?\d+(?:\.\d+)?)", line)
    if m:
        return float(m.group(1))
    # Si no, cualquier primer float
    m2 = re.search(r"([+-]?\d+(?:\.\d+)?)", line)
    if m2:
        return float(m2.group(1))
    return None

@dataclass
class Sample:
    t_rel: float
    V: float
    pH_tp: float
    pH_nernst: float

# ---------------------------
# Estado (buffers circulares)
# ---------------------------
MAX_BUFFER = 10000
if "t0" not in st.session_state:
    st.session_state.t0 = time.time()

if "buf_V" not in st.session_state:
    st.session_state.buf_V = deque(maxlen=MAX_BUFFER)
    st.session_state.buf_pH_tp = deque(maxlen=MAX_BUFFER)
    st.session_state.buf_pH_nernst = deque(maxlen=MAX_BUFFER)
    st.session_state.buf_t = deque(maxlen=MAX_BUFFER)

# Serial en estado
if "ser" not in st.session_state:
    st.session_state.ser = None
if "serial_connected" not in st.session_state:
    st.session_state.serial_connected = False

# ---------------------------
# Sidebar: Fuente y controles
# ---------------------------
st.sidebar.header("Fuente de datos")
source = st.sidebar.selectbox("Origen", ["Simulador", "Serial (Arduino)"])

if source == "Serial (Arduino)":
    if serial is None:
        st.sidebar.error("pyserial no está instalado. Instala con: pip install pyserial")
    port = st.sidebar.text_input("Puerto (ej. COM3 / /dev/ttyACM0)", value="COM3")
    baud = st.sidebar.number_input("Baudios", min_value=1200, max_value=115200, value=115200, step=1200)
    timeout_s = st.sidebar.number_input("Timeout lectura (s)", min_value=0.05, max_value=2.0, value=0.2, step=0.05)
    colb1, colb2 = st.sidebar.columns(2)
    if colb1.button("Conectar"):
        try:
            if st.session_state.ser:
                try:
                    st.session_state.ser.close()
                except Exception:
                    pass
            st.session_state.ser = serial.Serial(port=port, baudrate=int(baud), timeout=float(timeout_s))
            st.session_state.serial_connected = True
            st.sidebar.success(f"Conectado a {port}")
        except Exception as e:
            st.sidebar.error(f"No se pudo conectar: {e}")
            st.session_state.serial_connected = False
            st.session_state.ser = None
    if colb2.button("Desconectar"):
        try:
            if st.session_state.ser:
                st.session_state.ser.close()
        except Exception:
            pass
        st.session_state.serial_connected = False
        st.session_state.ser = None

st.sidebar.header("Ventana y refresco")
window = st.sidebar.number_input("Muestras a visualizar", min_value=10, max_value=MAX_BUFFER, value=60, step=10)
refresh_ms = st.sidebar.slider("Periodo de actualización (ms)", min_value=100, max_value=2000, value=500, step=50)
auto_update = st.sidebar.toggle("Actualizar automáticamente", value=True)

st.sidebar.header("Calibración 2 puntos")
pH1 = st.sidebar.number_input("pH1", value=7.00, step=0.01, format="%.2f")
V1 = st.sidebar.number_input("V1 (V @ pH1)", value=2.500, step=0.001, format="%.3f")
pH2 = st.sidebar.number_input("pH2", value=4.00, step=0.01, format="%.2f")
V2 = st.sidebar.number_input("V2 (V @ pH2)", value=3.000, step=0.001, format="%.3f")

st.sidebar.header("Nernst")
temp_c = st.sidebar.number_input("Temperatura (°C)", value=25.0, step=0.1)
E0 = st.sidebar.number_input("E0 (V @ pH 7)", value=2.500, step=0.001, format="%.3f")
sign = -1  # típico electrodo: V ↓ cuando pH ↑

if st.sidebar.button("Reset buffers"):
    st.session_state.buf_V.clear()
    st.session_state.buf_pH_tp.clear()
    st.session_state.buf_pH_nernst.clear()
    st.session_state.buf_t.clear()
    st.session_state.t0 = time.time()
    st.rerun()

# ---------------------------
# Lectura de una muestra
# ---------------------------
def read_sample_sim() -> float:
    t = time.time() - st.session_state.t0
    # señal base con ligera variación
    return 2.97 + 0.005 * math.sin(2 * math.pi * t / 40.0)

def read_sample_serial() -> Optional[float]:
    if not st.session_state.serial_connected or st.session_state.ser is None:
        return None
    try:
        line = st.session_state.ser.readline().decode(errors="ignore").strip()
        if not line:
            return None
        V = parse_voltage_from_line(line)
        return V
    except SerialException:
        return None
    except Exception:
        return None

def acquire_voltage() -> Optional[float]:
    if source == "Simulador":
        return read_sample_sim()
    else:
        return read_sample_serial()

# ---------------------------
# Actualizar buffers (1 muestra/ejecución)
# ---------------------------
V = acquire_voltage()
t_rel = round(time.time() - st.session_state.t0, 3)
if V is not None:
    ph_tp_val = ph_two_point(V, pH1, V1, pH2, V2)
    ph_nernst_val = ph_nernst(V, E0, temp_c, sign=sign)

    st.session_state.buf_V.append(V)
    st.session_state.buf_pH_tp.append(ph_tp_val)
    st.session_state.buf_pH_nernst.append(ph_nernst_val)
    st.session_state.buf_t.append(t_rel)

# ---------------------------
# DataFrames
# ---------------------------
df = pd.DataFrame({
    "t_rel": list(st.session_state.buf_t),
    "V": list(st.session_state.buf_V),
    "pH_tp": list(st.session_state.buf_pH_tp),
    "pH_nernst": list(st.session_state.buf_pH_nernst),
})
df_vis = df.tail(int(window)).reset_index(drop=True)

# ---------------------------
# UI
# ---------------------------
st.title("Monitor de pH y Voltaje (Arduino → Streamlit)")

col1, col2 = st.columns(2)
volt_placeholder = col1.empty()
ph_placeholder = col2.empty()
status_placeholder = st.empty()
table_placeholder = st.empty()

# Gráfico de Voltaje
if not df_vis.empty:
    volt_placeholder.line_chart(
        df_vis.set_index("t_rel")[["V"]],
        width='stretch',
        height=280,
    )
    col1.caption("Voltaje (V)")

# Gráfico de pH (dos curvas)
if not df_vis.empty:
    ph_placeholder.line_chart(
        df_vis.set_index("t_rel")[["pH_tp", "pH_nernst"]],
        width='stretch',
        height=280,
    )
    col2.caption("pH (calibración 2 puntos vs Nernst)")

# Estado actual
if not df.empty:
    last = df.iloc[-1]
    status_placeholder.markdown(
        f"**Último →** t={last['t_rel']:.1f}s | V={last['V']:.4f} V | "
        f"pH(2p)={last['pH_tp']:.3f} | pH(Nernst)={last['pH_nernst']:.3f} | "
        f"S_Nernst={nernst_slope_volt_per_pH(temp_c):.5f} V/pH"
    )

# Tabla (ventana)
table_placeholder.dataframe(df_vis, width='stretch', height=320)

# ---------------------------
# Auto-refresh sin apilar
# ---------------------------
if auto_update:
    time.sleep(refresh_ms / 1000.0)
    st.rerun()
