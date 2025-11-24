# app_ph_stream.py
import time
import threading
import queue
from dataclasses import dataclass
import pandas as pd
import serial
import serial.tools.list_ports
import streamlit as st

# --------------------------- Utilidades ---------------------------

@dataclass
class CalibParams:
    pH1: float = 7.00
    V1: float = 2.500
    pH2: float = 4.00
    V2: float = 2.677
    tempC: float = 25.0   # para mostrar y usar Nernst opcional

    @property
    def a_gain(self) -> float:
        # pendiente de 2 puntos (robusta frente a error de VREF)
        return (self.pH2 - self.pH1) / (self.V2 - self.V1)

    @property
    def b_off(self) -> float:
        return self.pH1 - self.a_gain * self.V1

    def ph_from_voltage(self, V: float) -> float:
        return self.a_gain * V + self.b_off

# --------------------------- Hilo lector --------------------------

class SerialReader(threading.Thread):
    def __init__(self, port: str, baud: int, out_queue: queue.Queue, stop_event: threading.Event):
        super().__init__(daemon=True)
        self.port = port
        self.baud = baud
        self.out = out_queue
        self.stop_event = stop_event
        self.ser = None

    def run(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=1)
            # limpia el buffer inicial
            self.ser.reset_input_buffer()
        except Exception as e:
            self.out.put(("__ERROR__", str(e)))
            return

        while not self.stop_event.is_set():
            try:
                line = self.ser.readline().decode(errors="ignore").strip()
                if not line:
                    continue
                # Formato esperado: "V,pH_cal,pH_nernst"
                parts = line.split(",")
                if len(parts) >= 3:
                    V = float(parts[0])
                    pH_cal = float(parts[1])
                    pH_nernst = float(parts[2])
                    self.out.put(("DATA", time.time(), V, pH_cal, pH_nernst))
                else:
                    # si viene texto de diagnóstico, lo enviamos como LOG
                    self.out.put(("LOG", line))
            except Exception as e:
                self.out.put(("__ERROR__", str(e)))
                break

        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        except Exception:
            pass

# --------------------------- Estado Streamlit ---------------------

if "running" not in st.session_state:
    st.session_state.running = False
if "data" not in st.session_state:
    st.session_state.data = []  # lista de dicts
if "reader" not in st.session_state:
    st.session_state.reader = None
if "q" not in st.session_state:
    st.session_state.q = queue.Queue()
if "stop_event" not in st.session_state:
    st.session_state.stop_event = threading.Event()
if "calib" not in st.session_state:
    st.session_state.calib = CalibParams()

# --------------------------- Sidebar: conexión --------------------

st.title("Monitor de pH y Voltaje (Arduino → Streamlit)")

with st.sidebar:
    st.header("Conexión serial")
    # listar puertos disponibles
    def list_ports():
        ports = [p.device for p in serial.tools.list_ports.comports()]
        # agrega opción vacía si no hay puertos
        return ports if ports else ["(sin puertos)"]

    ports = list_ports()
    port = st.selectbox("Puerto COM / tty", options=ports, index=0)
    baud = st.selectbox("Baudrate", options=[9600, 115200], index=0)

    col_b = st.columns(2)
    if col_b[0].button("Conectar", type="primary", disabled=st.session_state.running or "(sin puertos)" in port):
        st.session_state.stop_event.clear()
        st.session_state.q = queue.Queue()
        st.session_state.reader = SerialReader(port, baud, st.session_state.q, st.session_state.stop_event)
        st.session_state.reader.start()
        st.session_state.running = True

    if col_b[1].button("Desconectar", disabled=not st.session_state.running):
        st.session_state.stop_event.set()
        st.session_state.running = False

    st.divider()
    st.caption("Si no ves tu COM, desconecta/conecta el USB y pulsa Re-scan.")
    if st.button("Re-scan puertos"):
        st.experimental_rerun()

# --------------------------- Sidebar: calibración -----------------

with st.sidebar:
    st.header("Calibración (2 puntos)")
    pH1 = st.number_input("pH1", value=st.session_state.calib.pH1, step=0.01, format="%.2f")
    V1  = st.number_input("V1 (V@pH1)", value=st.session_state.calib.V1, step=0.001, format="%.3f")
    pH2 = st.number_input("pH2", value=st.session_state.calib.pH2, step=0.01, format="%.2f")
    V2  = st.number_input("V2 (V@pH2)", value=st.session_state.calib.V2, step=0.001, format="%.3f")
    tempC = st.number_input("Temperatura (°C)", value=st.session_state.calib.tempC, step=0.1, format="%.1f")
    use_local_cal = st.toggle("Re-calcular pH localmente desde V", value=True,
                              help="Si está activo, se calcula pH_local = a*V + b con los parámetros de esta sección.")
    if st.button("Aplicar calibración"):
        st.session_state.calib = CalibParams(pH1=pH1, V1=V1, pH2=pH2, V2=V2, tempC=tempC)
        st.success(f"Calibración aplicada. a={st.session_state.calib.a_gain:.4f}, b={st.session_state.calib.b_off:.4f}")

# --------------------------- Ingesta de datos ---------------------

log_box = st.container()
plot_place = st.container()
stats_box = st.container()
table_place = st.container()

# vaciar la cola del hilo al dataframe
def drain_queue_to_buffer():
    n_added = 0
    while True:
        try:
            item = st.session_state.q.get_nowait()
        except queue.Empty:
            break

        kind = item[0]
        if kind == "DATA":
            _, t, V, pH_cal, pH_nernst = item
            rec = {"t": t, "V": V, "pH_arduino": pH_cal, "pH_nernst": pH_nernst}
            # pH local usando calibración 2 puntos si procede
            if use_local_cal:
                rec["pH_local"] = st.session_state.calib.ph_from_voltage(V)
            st.session_state.data.append(rec)
            n_added += 1
        elif kind == "LOG":
            log_box.write(f"LOG: {item[1]}")
        elif kind == "__ERROR__":
            st.error(f"Serial error: {item[1]}")
            st.session_state.stop_event.set()
            st.session_state.running = False
            break
    return n_added

# Limitar buffer a N puntos para no crecer indefinidamente
MAX_POINTS = 4000

def get_df():
    if not st.session_state.data:
        return pd.DataFrame(columns=["t", "V", "pH_arduino", "pH_nernst", "pH_local"])
    df = pd.DataFrame(st.session_state.data)
    if len(df) > MAX_POINTS:
        df = df.iloc[-MAX_POINTS:].reset_index(drop=True)
        st.session_state.data = df.to_dict(orient="records")
    # eje tiempo relativo en segundos
    if not df.empty:
        t0 = df["t"].iloc[0]
        df["t_rel"] = df["t"] - t0
    return df

# --------------------------- Loop de refresco ---------------------

placeholder = st.empty()
autorefresh = st.toggle("Auto-refrescar gráficos", value=True)

# Un pequeño loop para actualizar mientras está conectado
for _ in range(200):  # ~200 * 0.2s = 40s por ejecución; se reinicia al interactuar
    if st.session_state.running:
        added = drain_queue_to_buffer()
        df = get_df()
        with plot_place:
            if not df.empty:
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("Voltaje (V)")
                    st.line_chart(df.set_index("t_rel")[["V"]])
                with col2:
                    st.subheader("pH")
                    ph_cols = ["pH_arduino"]
                    if "pH_local" in df.columns and use_local_cal:
                        ph_cols.append("pH_local")
                    st.line_chart(df.set_index("t_rel")[ph_cols])

        with stats_box:
            if not df.empty:
                last = df.iloc[-1]
                st.write(
                    f"**Último** → t={last['t_rel']:.1f}s | V={last['V']:.4f} V | "
                    f"pH_arduino={last['pH_arduino']:.3f}"
                    + (f" | pH_local={last.get('pH_local', float('nan')):.3f}" if use_local_cal else "")
                )

        time.sleep(0.2)
        if not autorefresh:
            break
    else:
        break

# --------------------------- Tabla y descarga ---------------------

df_final = get_df()
with table_place:
    st.subheader("Datos")
    st.dataframe(df_final.drop(columns=["t"]), use_container_width=True)
    if not df_final.empty:
        csv = df_final.drop(columns=["t"]).to_csv(index=False).encode()
        st.download_button("Descargar CSV", data=csv, file_name="ph_stream.csv", mime="text/csv")
