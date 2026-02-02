# test2.py
# ------------------------------------------------------------
# Monitor de pH y Voltaje (Arduino → Streamlit)
# - Imagen en sidebar
# - Serial o Simulador
# - Ventana deslizante (N muestras)
# - Placeholders (no apilar charts)
# - Descarga CSV sin MediaFileHandler
# - Calibración 2 puntos + Nernst
# - st.rerun() y width='stretch'
# ------------------------------------------------------------

import math
import re
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

import pandas as pd
import streamlit as st

# --- Ajusta la ruta de tu imagen (logo o encabezado) ---
SIDEBAR_IMAGE_PATH = "./imgs/logo_upch.png"

# pyserial opcional
try:
    import serial
    from serial import SerialException
    from serial.tools import list_ports
except Exception:
    serial = None
    SerialException = Exception
    list_ports = None

# ---------------------------
# Configuración general
# ---------------------------
st.set_page_config(page_title="pHScope", layout="wide")

# Imagen en sidebar (si existe la ruta)
try:
    st.sidebar.image(SIDEBAR_IMAGE_PATH)
except Exception:
    st.sidebar.caption("Sube/ajusta la imagen del encabezado (opcional).")

# ---------------------------
# Constantes electroquímicas
# ---------------------------
R = 8.31446261815324       # J/(mol·K)
F = 96485.33212            # C/mol
LN10 = math.log(10.0)

def nernst_slope_volt_per_pH(temp_c: float) -> float:
    """Pendiente Nernst (V/pH) = (R*T/F)*ln(10). A 25°C ≈ 0.05916 V/pH."""
    T = temp_c + 273.15
    return (R * T / F) * LN10

def ph_two_point(volts: float, pH1: float, V1: float, pH2: float, V2: float) -> float:
    """Calibración lineal por dos puntos: pH = a*V + b"""
    if abs(V2 - V1) < 1e-12:
        return float("nan")
    a = (pH2 - pH1) / (V2 - V1)
    b = pH1 - a * V1
    return a * volts + b

def ph_nernst(volts: float, E0: float, temp_c: float, sign: int = -1) -> float:
    """Modelo Nernst: pH = 7 + sign*(E - E0)/S, S = pendiente Nernst (V/pH)"""
    S = nernst_slope_volt_per_pH(temp_c)
    if S <= 0:
        return float("nan")
    return 7.0 + sign * (volts - E0) / S

_MAC_RE = re.compile(r"\b[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}\b")

def parse_measurements_from_line(line: str) -> Dict[str, Any]:
    """
    Intenta extraer mediciones desde una línea enviada por Serial.

    Soporta formatos típicos, por ejemplo:
      - "V=2.9734" / "V:2.9734" / "2.9734"
      - "ADC:797 Voltage:0.642V pH:19.26"
      - "ADC Value: 797 | Measured Voltage: 0.642V | pH: 19.26"
      - '[SERVER] Recibido de e8:.. -> ADC:797 Voltage:0.642V pH:19.26'
      - '{"V":2.97,"pH":7.01}'
    """
    out: Dict[str, Any] = {"V": None, "pH": None, "ADC": None, "raw": line}

    m_adc = re.search(r"\bADC(?:\s*Value)?\s*[:=]\s*(\d+)\b", line, flags=re.IGNORECASE)
    if m_adc:
        out["ADC"] = int(m_adc.group(1))

    m_ph = re.search(r"\bpH\s*[:=]\s*([+-]?\d+(?:\.\d+)?)\b", line, flags=re.IGNORECASE)
    if m_ph:
        out["pH"] = float(m_ph.group(1))

    m_v = re.search(
        r"(?:Measured\s*Voltage|Real\s*Voltage|Voltage)\s*[:=]\s*([+-]?\d+(?:\.\d+)?)\s*V?\b",
        line,
        flags=re.IGNORECASE,
    )
    if m_v:
        out["V"] = float(m_v.group(1))
        return out

    m_v2 = re.search(r"\b[Vv]\s*[:=]\s*([+-]?\d+(?:\.\d+)?)\b", line)
    if m_v2:
        out["V"] = float(m_v2.group(1))
        return out

    m_json_v = re.search(r"\"V\"\s*:\s*([+-]?\d+(?:\.\d+)?)", line)
    if m_json_v:
        out["V"] = float(m_json_v.group(1))
        return out

    # Fallback: solo cuando la línea NO parece un log con MAC (evita confundir "e8:27:..." con un valor).
    if not _MAC_RE.search(line) and "Recibido de" not in line:
        m_f = re.search(r"([+-]?\d+(?:\.\d+)?)", line)
        if m_f:
            out["V"] = float(m_f.group(1))
    return out

def parse_voltage_from_line(line: str) -> Optional[float]:
    return parse_measurements_from_line(line).get("V")

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
if "buf_pH_rx" not in st.session_state:
    st.session_state.buf_pH_rx = deque(maxlen=MAX_BUFFER)
if "buf_adc" not in st.session_state:
    st.session_state.buf_adc = deque(maxlen=MAX_BUFFER)
if "last_rx" not in st.session_state:
    st.session_state.last_rx = {"raw": "", "V": None, "pH": None, "ADC": None}

# Estado de Serial
if "ser" not in st.session_state:
    st.session_state.ser = None
if "serial_connected" not in st.session_state:
    st.session_state.serial_connected = False
if "cached_ports" not in st.session_state:
    st.session_state.cached_ports = []

# ---------------------------
# Sidebar: Fuente y controles
# ---------------------------
st.sidebar.header("Conexión serial")

def list_serial_ports() -> List[str]:
    if list_ports is None:
        return []
    return [p.device for p in list_ports.comports()]

if st.session_state.cached_ports == []:
    st.session_state.cached_ports = list_serial_ports()

port = st.sidebar.selectbox(
    "Puerto COM / tty",
    options=st.session_state.cached_ports if st.session_state.cached_ports else ["COM3"],
    index=0
)
baud = st.sidebar.selectbox("Baudrate", options=[9600, 19200, 38400, 57600, 115200], index=0)
colb1, colb2, colb3 = st.sidebar.columns([1, 1, 1])

if colb1.button("Conectar", use_container_width=False, key="btn_connect"):
    if serial is None:
        st.sidebar.error("pyserial no está instalado: pip install pyserial")
    else:
        try:
            if st.session_state.ser:
                try:
                    st.session_state.ser.close()
                except Exception:
                    pass
            st.session_state.ser = serial.Serial(port=str(port), baudrate=int(baud), timeout=0.2)
            st.session_state.serial_connected = True
            st.sidebar.success(f"Conectado a {port}")
        except Exception as e:
            st.sidebar.error(f"No se pudo conectar: {e}")
            st.session_state.serial_connected = False
            st.session_state.ser = None

if colb2.button("Desconectar", use_container_width=False, key="btn_disconnect"):
    try:
        if st.session_state.ser:
            st.session_state.ser.close()
    except Exception:
        pass
    st.session_state.serial_connected = False
    st.session_state.ser = None

if colb3.button("Re-scan puertos", use_container_width=False, key="btn_rescan"):
    st.session_state.cached_ports = list_serial_ports()
    st.rerun()

st.sidebar.header("Adquisición / visualización")
source = st.sidebar.selectbox("Origen", ["Serial (Arduino)", "Simulador"], index=0)
window = st.sidebar.number_input("Muestras a visualizar", min_value=10, max_value=MAX_BUFFER, value=60, step=10)
refresh_ms = st.sidebar.slider("Periodo de actualización (ms)", min_value=100, max_value=2000, value=500, step=50)
auto_update = st.sidebar.toggle("Actualizar automáticamente", value=True)

st.sidebar.header("Calibración (2 puntos)")
pH1 = st.sidebar.number_input("pH1", value=7.00, step=0.01, format="%.2f")
V1 = st.sidebar.number_input("V1 (V @ pH1)", value=2.500, step=0.001, format="%.3f")
pH2 = st.sidebar.number_input("pH2", value=4.00, step=0.01, format="%.2f")
V2 = st.sidebar.number_input("V2 (V @ pH2)", value=3.000, step=0.001, format="%.3f")

st.sidebar.header("Nernst")
temp_c = st.sidebar.number_input("Temperatura (°C)", value=25.0, step=0.1)
E0 = st.sidebar.number_input("E0 (V @ pH 7)", value=2.500, step=0.001, format="%.3f")
sign = -1  # normalmente V disminuye cuando pH aumenta

if st.sidebar.button("Reset buffers"):
    st.session_state.buf_V.clear()
    st.session_state.buf_pH_tp.clear()
    st.session_state.buf_pH_nernst.clear()
    st.session_state.buf_t.clear()
    st.session_state.buf_pH_rx.clear()
    st.session_state.buf_adc.clear()
    st.session_state.t0 = time.time()
    st.rerun()

# ---------------------------
# Lectura de una muestra
# ---------------------------
def read_sample_sim() -> float:
    t = time.time() - st.session_state.t0
    v = 2.97 + 0.005 * math.sin(2 * math.pi * t / 40.0)
    st.session_state.last_rx = {"raw": "SIM", "V": v, "pH": None, "ADC": None}
    return v

def read_sample_serial() -> Optional[float]:
    if not st.session_state.serial_connected or st.session_state.ser is None:
        return None
    try:
        line = st.session_state.ser.readline().decode(errors="ignore").strip()
        if not line:
            return None
        parsed = parse_measurements_from_line(line)
        st.session_state.last_rx = parsed
        return parsed.get("V")
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
# Actualizar buffers (1 muestra por ejecución)
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
    st.session_state.buf_pH_rx.append(st.session_state.last_rx.get("pH"))
    st.session_state.buf_adc.append(st.session_state.last_rx.get("ADC"))

# ---------------------------
# DataFrames
# ---------------------------
df = pd.DataFrame({
    "t_rel": list(st.session_state.buf_t),
    "V": list(st.session_state.buf_V),
    "pH_2p": list(st.session_state.buf_pH_tp),
    "pH_nernst": list(st.session_state.buf_pH_nernst),
    "pH_rx": list(st.session_state.buf_pH_rx),
    "ADC": list(st.session_state.buf_adc),
})
df_vis = df.tail(int(window)).reset_index(drop=True)

# ---------------------------
# UI principal
# ---------------------------
st.title("pHScope: Monitor de pH para saliva artificial")

col1, col2 = st.columns(2)
volt_placeholder = col1.empty()
ph_placeholder = col2.empty()
status_placeholder = st.empty()
table_placeholder = st.empty()

# Gráfico de Voltaje
if not df_vis.empty:
    volt_placeholder.line_chart(
        df_vis.set_index("t_rel")[["V"]],
        use_container_width=True,
        height=280,
    )
    col1.caption("Voltaje (V)")

# Gráfico de pH (dos curvas)
if not df_vis.empty:
    ph_cols = ["pH_2p", "pH_nernst"]
    if "pH_rx" in df_vis.columns and df_vis["pH_rx"].notna().any():
        ph_cols.append("pH_rx")
    ph_placeholder.line_chart(
        df_vis.set_index("t_rel")[ph_cols],
        use_container_width=True,
        height=280,
    )
    col2.caption("pH (calibración 2 puntos vs Nernst)")

# Estado actual
if not df.empty:
    last = df.iloc[-1]
    S_N = nernst_slope_volt_per_pH(temp_c)
    rx_ph_txt = ""
    if "pH_rx" in last and pd.notna(last["pH_rx"]):
        rx_ph_txt = f" | pH(rx)={float(last['pH_rx']):.3f}"
    status_placeholder.markdown(
        f"**Último →** t={last['t_rel']:.1f}s | V={last['V']:.4f} V | "
        f"pH(2p)={last['pH_2p']:.3f} | pH(Nernst)={last['pH_nernst']:.3f}{rx_ph_txt} | "
        f"S_Nernst={S_N:.5f} V/pH"
    )

# Tabla (ventana)
table_placeholder.dataframe(df_vis, use_container_width=True, height=320)

# Botones de descarga (sin MediaFileHandler)
col_d1, col_d2 = st.columns(2)
with col_d1:
    st.download_button(
        "⬇️ Ventana (CSV)",
        df_vis.to_csv(index=False).encode("utf-8"),
        file_name="ph_window.csv",
        mime="text/csv",
        key="dl_window_csv"
    )
with col_d2:
    st.download_button(
        "⬇️ Histórico (CSV)",
        df.to_csv(index=False).encode("utf-8"),
        file_name="ph_history.csv",
        mime="text/csv",
        key="dl_full_csv"
    )

# ---------------------------
# Auto-refresh sin apilar
# ---------------------------
if auto_update:
    time.sleep(refresh_ms / 1000.0)
    st.rerun()
