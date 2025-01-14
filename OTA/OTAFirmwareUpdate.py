import asyncio
import zlib
from bleak import BleakClient, BleakScanner
import time

# Macro definitions
MAX_FILE_SIZE = 300 * 1024  # Maximum file size in bytes (100 KB)
CHUNK_SIZE = 112             # Number of bytes per chunk; adjust if needed
BLE_DEVICE_ADDRESS = "C2:9E:73:16:D8:2A"  # Replace with the Bluetooth address of the STM32
BLE_DEVICE_ADDRESS1 = "D1:AC:A6:02:60:FB"  # Replace with the Bluetooth address of the STM32
devices = {"DNode2":BLE_DEVICE_ADDRESS,"DNode4":BLE_DEVICE_ADDRESS1}
SERVICE_UUID = "00000000-000e-11e1-9ab4-0002a5d5c51b"        # Replace with your STM32 BLE service UUID
CHARACTERISTIC_UUID = "00000001-000e-11e1-ac36-0002a5d5c51b"  # Replace with the characteristic UUID for data transfer

fsiz = 0
ADDRESS = 0

def bytes_to_32bit_chunks(byte_data):
    # Ensure the byte data length is a multiple of 4 by padding with zeros if necessary
    while len(byte_data) % 4 != 0:
        byte_data += b'\x00'
    
    # Convert 4 bytes into a single 32-bit integer
    data_buffer = [
        int.from_bytes(byte_data[i:i+4], byteorder='little')
        for i in range(0, len(byte_data), 4)
    ]
    return data_buffer

def crc32_multi(crc, data_buffer):
    for data in data_buffer:
        crc ^= data  # Initial XOR operation
        for _ in range(32):
            if crc & 0x80000000:
                crc = (crc << 1) ^ 0x04C11DB7  # Polynomial used in STM32
            else:
                crc = (crc << 1)
            crc &= 0xFFFFFFFF  # Ensure crc remains a 32-bit value
        # print(f"len: {len(data_buffer)} data: {data:08x} CFC : {crc:08x}")
    return crc

async def send_firmware(filename: str):
    
    ''' ******************* '''
    ''' SCAN FOR THE DEVICE '''
    ''' ******************* '''
    
    print("Scanning for available Bluetooth devices...")
    devices = await BleakScanner.discover()
    if not devices:
        print("No Bluetooth devices found.")
        ADDRESS = None

    print("Available Bluetooth devices:")
    for idx, device in enumerate(devices, start=1):
        print(f"{idx}. {device.name} ({device.address})")

    try:
        selection = int(input("Select a device by number: "))
        if 1 <= selection <= len(devices):
            selected_device = devices[selection - 1]
            print(f"Selected device: {selected_device.name} ({selected_device.address})")
            ADDRESS =  selected_device.address
        else:
            print("Invalid selection.")
            ADDRESS =  None
    except ValueError:
        print("Invalid input.")
        ADDRESS =  None

    if(ADDRESS != None):

        ''' ********************** '''
        ''' CHECK FOR THE FIRMWARE '''
        ''' ********************** '''
        try:
            # Read the firmware file
            with open(filename, 'rb') as file:
                firmware_data = file.read()
                firmware_len = len(firmware_data)
                if firmware_len > MAX_FILE_SIZE:
                    print("Error: Firmware file exceeds maximum allowed size.")
                    return
                firm_rs2_len = int(firmware_len/4)
                print(f"Firmware size: {firmware_len} bytes --- Firmware size/ 4: {firm_rs2_len} bytes")
                aDataBuffer = bytes_to_32bit_chunks(firmware_data)
                # Prepare the upgrade command
                command_str = "upgradeFw".encode('utf-8')
                file_size_bytes = firmware_len.to_bytes(4, byteorder='little')
                # crc_bytes = zlib.crc32(firmware_data).to_bytes(4, byteorder='little')
                crc_bytes = crc32_multi(0xFFFFFFFF, aDataBuffer).to_bytes(4, byteorder='little')
                # print("")
                crc_bytes_fgs = crc32_multi(0xFFFFFFFF, aDataBuffer)
                upgrade_command = command_str + file_size_bytes + crc_bytes
                print(f"Upgrade command (raw bytes): {crc_bytes_fgs:08x}")
        except FileNotFoundError:
            print("Error: Firmware file not found.")
            return


        ''' *************************************** '''
        ''' CONNECT TO THE DEVICE AND SEND FIRMWARE '''
        ''' *************************************** '''
        
        # Connect to the STM32 device via Bluetooth
        # print(f"Address in function {ADDRESS}")
        async with BleakClient(ADDRESS) as client:
            try:
                print(f"Attempting to connect to STM32 device address {ADDRESS}...")
                if  client.is_connected:
                    print("Connection established successfully.")
                    
                    # Ask for user confirmation before transmission
                    confirm = input("Do you want to proceed with the firmware transmission? (yes/no): ").strip().lower()
                    if confirm != "yes":
                        print("Firmware transmission aborted.")
                        if await client.disconnect():
                            return
                    # Send the upgrade command
                    await client.write_gatt_char(CHARACTERISTIC_UUID, upgrade_command)
                    # print("Upgrade command sent successfully.")
                    
                    # Send firmware in chunks
                    total_chunks = (len(firmware_data) + CHUNK_SIZE - 1) // CHUNK_SIZE
                    fsiz = len(firmware_data)
                    for i in range(total_chunks):
                        start = i * CHUNK_SIZE
                        end = min(start + CHUNK_SIZE, len(firmware_data))
                        chunk = firmware_data[start:end]

                        # Write the chunk to the BLE characteristic
                        await client.write_gatt_char(CHARACTERISTIC_UUID, chunk)
                        
                        print(f"Sent chunk {i + 1}/{total_chunks} , {fsiz}")
                        fsiz = fsiz - CHUNK_SIZE
                        time.sleep(0.2)

                    print("Firmware update completed successfully.")
                else:
                    print("Failed to connect to the STM32 device. Please check the Bluetooth connection.")
                time.sleep(10)
            except KeyboardInterrupt:
                print("Keyboard Interrupt")
    else:
        print("Terminating")

# Run the firmware transmission asynchronously
filename = "firmware.bin"  # Replace with your firmware binary file path
asyncio.run(send_firmware(filename))


