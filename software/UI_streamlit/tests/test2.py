# app_ph_stream.py
import time
import threading
import queue
from dataclasses import dataclass

import pandas as pd
import serial
import serial.tools.list_ports
import streamlit as st

# =========================== Estado inicial ===========================
if "running" not in st.session_state:
    st.session_state.running = False
if "reader" not in st.session_state:
    st.session_state.reader = None
if "q" not in st.session_state:
    st.session_state.q = queue.Queue()
if "stop_event" not in st.session_state:
    st.session_state.stop_event = threading.Event()
if "data" not in st.session_state:
    st.session_state.data = []  # registros {t, V, pH_arduino, pH_nernst, pH_local}

# =========================== Calibración ==============================
@dataclass
class CalibParams:
    pH1: float = 7.00
    V1: float = 2.500
    pH2: float = 4.00
    V2: float = 2.677
    tempC: float = 25.0

    @property
    def a_gain(self) -> float:
        return (self.pH2 - self.pH1) / (self.V2 - self.V1)

    @property
    def b_off(self) -> float:
        return self.pH1 - self.a_gain * self.V1

    def ph_from_voltage(self, V: float) -> float:
        return self.a_gain * V + self.b_off

if "calib" not in st.session_state:
    st.session_state.calib = CalibParams()

# =========================== Serial Reader (hilo) =====================
class SerialReader(threading.Thread):
    def __init__(self, port: str, baud: int, out_q: queue.Queue, stop_event: threading.Event):
        super().__init__(daemon=True)
        self.port = port
        self.baud = baud
        self.out_q = out_q
        self.stop_event = stop_event
        self.ser = None

    def run(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=1)
            self.ser.reset_input_buffer()
        except Exception as e:
            self.out_q.put(("__ERROR__", f"No se pudo abrir {self.port}: {e}"))
            return

        while not self.stop_event.is_set():
            try:
                line = self.ser.readline().decode(errors="ignore").strip()
                if not line:
                    continue
                parts = line.split(",")
                if len(parts) >= 3:
                    V = float(parts[0])
                    pH_cal = float(parts[1])
                    pH_nernst = float(parts[2])
                    self.out_q.put(("DATA", time.time(), V, pH_cal, pH_nernst))
                else:
                    self.out_q.put(("LOG", line))
            except Exception as e:
                self.out_q.put(("__ERROR__", f"Lectura falló: {e}"))
                break

        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        except Exception:
            pass

# =========================== UI lateral ==============================
st.title("Monitor de pH y Voltaje (Arduino → Streamlit)")

with st.sidebar:
    st.header("Conexión serial")

    def list_ports():
        ports = [p.device for p in serial.tools.list_ports.comports()]
        return ports if ports else ["(sin puertos)"]

    ports = list_ports()
    port = st.selectbox("Puerto COM / tty", options=ports, index=0)
    baud = st.selectbox("Baudrate", options=[9600, 115200], index=0)

    colb = st.columns(2)
    if colb[0].button("Conectar", type="primary",
                      disabled=st.session_state.running or "(sin puertos)" in port):
        if st.session_state.reader and st.session_state.reader.is_alive():
            st.warning("Ya hay una conexión activa.")
        else:
            st.session_state.stop_event.clear()
            st.session_state.q = queue.Queue()
            st.session_state.reader = SerialReader(port, baud, st.session_state.q, st.session_state.stop_event)
            st.session_state.reader.start()
            st.session_state.running = True

    if colb[1].button("Desconectar", disabled=not st.session_state.running):
        st.session_state.stop_event.set()
        st.session_state.running = False

    if st.button("Re-scan puertos"):
        st.experimental_rerun()

    st.divider()
    st.header("Calibración (2 puntos)")
    pH1 = st.number_input("pH1", value=st.session_state.calib.pH1, step=0.01, format="%.2f")
    V1  = st.number_input("V1 (V@pH1)", value=st.session_state.calib.V1, step=0.001, format="%.3f")
    pH2 = st.number_input("pH2", value=st.session_state.calib.pH2, step=0.01, format="%.2f")
    V2  = st.number_input("V2 (V@pH2)", value=st.session_state.calib.V2, step=0.001, format="%.3f")
    tempC = st.number_input("Temperatura (°C)", value=st.session_state.calib.tempC, step=0.1, format="%.1f")
    use_local_cal = st.toggle("Re-calcular pH localmente desde V", value=True)

    if st.button("Aplicar calibración"):
        st.session_state.calib = CalibParams(pH1=pH1, V1=V1, pH2=pH2, V2=V2, tempC=tempC)
        st.success(f"a={st.session_state.calib.a_gain:.4f}, b={st.session_state.calib.b_off:.4f}")

# =========================== Funciones de datos ======================
MAX_POINTS = 4000

def drain_queue_to_buffer():
    """Vacía la cola del hilo al buffer de session_state."""
    while True:
        try:
            item = st.session_state.q.get_nowait()
        except queue.Empty:
            break

        kind = item[0]
        if kind == "DATA":
            _, t, V, pH_cal, pH_nernst = item
            rec = {"t": t, "V": V, "pH_arduino": pH_cal, "pH_nernst": pH_nernst}
            if use_local_cal:
                rec["pH_local"] = st.session_state.calib.ph_from_voltage(V)
            st.session_state.data.append(rec)

        elif kind == "LOG":
            st.write(f"LOG: {item[1]}")

        elif kind == "__ERROR__":
            st.error(item[1])
            st.session_state.stop_event.set()
            st.session_state.running = False
            break

    # recorta buffer
    if len(st.session_state.data) > MAX_POINTS:
        st.session_state.data = st.session_state.data[-MAX_POINTS:]

def get_df():
    if not st.session_state.data:
        return pd.DataFrame(columns=["t", "V", "pH_arduino", "pH_nernst", "pH_local", "t_rel"])
    df = pd.DataFrame(st.session_state.data)
    t0 = df["t"].iloc[0]
    df["t_rel"] = df["t"] - t0
    return df

# =========================== Render único ===========================
# (sin bucles de pintado repetidos)
if st.session_state.running:
    drain_queue_to_buffer()

df = get_df()

plot_box = st.container()
stats_box = st.container()
table_box = st.container()

with plot_box:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Voltaje (V)")
        if not df.empty:
            st.line_chart(df.set_index("t_rel")[["V"]])
        else:
            st.info("Sin datos todavía...")
    with col2:
        st.subheader("pH")
        if not df.empty:
            ph_cols = ["pH_arduino"]
            if "pH_local" in df.columns and use_local_cal:
                ph_cols.append("pH_local")
            st.line_chart(df.set_index("t_rel")[ph_cols])
        else:
            st.info("Sin datos todavía...")

with stats_box:
    if not df.empty:
        last = df.iloc[-1]
        msg = (
            f"**Último** → t={last['t_rel']:.1f}s | V={last['V']:.4f} V | "
            f"pH_arduino={last['pH_arduino']:.3f}"
        )
        if "pH_local" in df.columns and use_local_cal:
            msg += f" | pH_local={last['pH_local']:.3f}"
        st.write(msg)

with table_box:
    st.subheader("Datos")
    if not df.empty:
        st.dataframe(df.drop(columns=["t"]),  width='stretch')
        csv = df.drop(columns=["t"]).to_csv(index=False).encode()
        st.download_button("Descargar CSV", data=csv, file_name="ph_stream.csv", mime="text/csv")
    else:
        st.caption("Aún no hay registros.")

# =========================== Auto-rerun =============================
refresh_ms = 500  # intervalo de refresco
autorefresh = st.toggle("Auto-refrescar gráficos", value=True,
                        help="Rerun periódico del script mientras esté conectado.")

if st.session_state.running and autorefresh:
    # pequeño retardo + rerun para actualizar sin duplicar gráficos
    time.sleep(refresh_ms / 1000.0)
    #st.experimental_rerun()
    st.rerun()

