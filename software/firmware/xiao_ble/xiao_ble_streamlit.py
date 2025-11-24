import asyncio
import streamlit as st
from bleak import BleakScanner, BleakClient
import re  # Para extraer los valores usando expresiones regulares

DEVICE_NAME = "XIAO_BLE"  # El nombre que configuraste en Arduino
UART_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
UART_RX_CHARACTERISTIC_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  # Característica para recibir datos

async def scan_for_device():
    devices = await BleakScanner.discover()
    for d in devices:
        if d.name == DEVICE_NAME:
            return d
    return None

async def read_uart_data():
    device = await scan_for_device()
    if device is None:
        st.error(f"No se encontró el dispositivo con nombre: {DEVICE_NAME}")
        return None

    try:
        client = BleakClient(device)
        await client.connect()
        st.success(f"Conectado a: {device.name}")

        def notification_handler(characteristic, data):
            data_str = data.decode('utf-8').strip()
            st.session_state.raw_data = data_str
            ph_match = re.search(r"pH: ([\d.]+)", data_str)
            voltage_match = re.search(r"Real Voltage: ([\d.]+)V", data_str)

            if ph_match:
                st.session_state.ph_value = float(ph_match.group(1))
            if voltage_match:
                st.session_state.voltage_value = float(voltage_match.group(1))

        await client.start_notify(UART_RX_CHARACTERISTIC_UUID, notification_handler)
        return client

    except Exception as e:
        st.error(f"Error de comunicación BLE: {e}")
        return None

async def main_loop():
    if 'client' not in st.session_state:
        st.session_state.client = await read_uart_data()
        st.session_state.ph_value = None
        st.session_state.voltage_value = None
        st.session_state.raw_data = ""

    ph_placeholder = st.empty()
    voltage_placeholder = st.empty()
    raw_data_placeholder = st.empty()

    while st.session_state.client is not None and st.session_state.client.is_connected:
        if st.session_state.ph_value is not None:
            ph_placeholder.metric("Valor de pH", f"{st.session_state.ph_value:.2f}")
        if st.session_state.voltage_value is not None:
            voltage_placeholder.metric("Voltaje Real", f"{st.session_state.voltage_value:.3f} V")
        raw_data_placeholder.info(f"Datos brutos: {st.session_state.raw_data}")
        await asyncio.sleep(1)
    else:
        ph_placeholder.error("No conectado al dispositivo BLE.")
        voltage_placeholder.empty()
        raw_data_placeholder.empty()

if __name__ == "__main__":
    st.title("Monitor de pH y Voltaje (BLE UART)")
    asyncio.run(main_loop())