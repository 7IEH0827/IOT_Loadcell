import json
import time
import requests
import serial.tools.list_ports
import threading
import uuid

# --- Configuration ---
BASE_URL_LASER = "http://localhost:8080/api/sensor/laser"
BASE_URL_LIQUID = 'http://localhost:8080/api/sensors/weight/liquids'
BASE_URL_CUP = 'http://localhost:8080/api/sensor/cup'
BASE_URL_SONIC = "http://localhost:8080/api/sensor/ultrasonic"
BASE_URL_IR = "http://localhost:8080/api/sensor/ir/events"

BIN_ID_DEFAULT = 2
LIVE_UUID = "LIVE"
TIMEOUT = 1
MAX_SAMPLES = 250
FRAGMENT_TIMEOUT = 10.0  # Seconds to wait for all fragments

# --- Global State ---
# Dictionary to store partial laser data: { uuid: { 'timestamp': time, 'samples': [None]*250, 'received_count': 0, 'binId': default } }
laser_buffers = {}
# Mapping from short 'id' (from TX) to full 'uuid' (for Server)
id_map = {}

# --- Serial Connection ---
ports = serial.tools.list_ports.comports()
print("=== Available COM Ports ===")
for port in ports:
    print(f"Port: {port.device}")
    print(f"Description: {port.description}")
    print(f"HWID: {port.hwid}")
    print("---------------------------")

ser = None
while True:
    time.sleep(0.1)
    portName = input("Enter the port name (or 'test' for test mode): ")
    if portName == "test":
        break
    try:
        ser = serial.Serial(
            port=portName,
            baudrate=115200,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=1
        )
        print(f"[OK] Connected to {portName}")
        break
    except Exception as e:
        print(f"[ERROR] Connection failed: {e}")

# --- Helper Functions ---

def request_Laser(assembled_data):
    """
    Sends the reassembled laser data to the server.
    assembled_data structure:
    {
        "uuid": "...",
        "binId": 1,
        "samples": [ {"distanceMm": 45, "timeMsec": 0}, ... ]
    }
    """
    try:
        print("\n" + "=" * 60)
        print("Sending LASER data to server...")
        print(f"URL: {BASE_URL_LASER}/insertion-event")
        print(f"UUID: {assembled_data.get('uuid')}")
        print(f"Samples: {len(assembled_data['samples'])} measurements")

        # The server expects a JSON with 'uuid', 'binId', 'samples', etc.
        # We might need to add 'binWidthMm' if the server requires it, or the server handles it.
        # Assuming server needs 'binId' and 'samples'.
        
        payload = {
            "uuid": assembled_data.get("uuid"),
            "binId": assembled_data.get("binId", BIN_ID_DEFAULT),
            "samples": assembled_data.get("samples"),
            # Add other fields if necessary, e.g., "binWidthMm": 100
        }

        response = requests.post(
            f"{BASE_URL_LASER}/insertion-event",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=5
        )

        if response.status_code == 200:
            result = response.json()
            print("\n[SUCCESS] Server Response!")
            print("=" * 60)

            if result.get('isSuccess'):
                res_data = result.get('result', {})
                print(f"Event ID: {res_data.get('uuid')}")
                print(f"Valid Cup: {res_data.get('isValidCup')}")
                print(f"Pattern: {res_data.get('patternType')} - {res_data.get('patternDescription')}")
                print(f"Diameter: {res_data.get('minDiameterMm'):.1f}mm -> {res_data.get('maxDiameterMm'):.1f}mm")

                if res_data.get('rejectionReason'):
                    print(f"[WARNING] Rejection: {res_data.get('rejectionReason')}")
            else:
                print(f"[ERROR] {result.get('message')}")
        else:
            print(f"[ERROR] HTTP Error {response.status_code}")
            print(f"Response: {response.text}")

        print("=" * 60 + "\n")

    except requests.exceptions.ConnectionError:
        print(f"[ERROR] Connection failed: Server not running at {BASE_URL_LASER}")
    except requests.exceptions.Timeout:
        print(f"[ERROR] Request timeout")
    except Exception as e:
        print(f"[ERROR] {e}")

def request_sonic(data):
    bin_id = data.get("binId", BIN_ID_DEFAULT)
    dist_cm = data.get("distanceCm")
    fill_rate = data.get("fillRate")
    event_uuid = data.get("uuid")

    if dist_cm is None or fill_rate is None:
        print("[WARN] JSON missing distanceCm/fillRate:", data)
        return

    uuid = event_uuid if event_uuid else LIVE_UUID

    payload = {
        "binId": bin_id,
        "uuid": uuid,
        "distanceCm": dist_cm,
        "fillRate": fill_rate,
    }

    try:
        print("\n" + "=" * 60)
        print("Sending SONIC data to server...")
        print(f"URL: {BASE_URL_SONIC}")
        print("Payload:", payload)

        resp = requests.post(
            BASE_URL_SONIC,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=5,
        )
        print(f"[HTTP] Status: {resp.status_code}")

    except Exception as e:
        print("[ERROR]", e)

def request_Cup(data):
    uuid_val = data.get("uuid")
    weight = data.get("weight")
    cup_type = data.get("type")

    if weight is None or weight <= 0:
        return

    payload = {
        "uuid": uuid_val,
        "binId": BIN_ID_DEFAULT,
        "weight": weight,
        "type": cup_type
    }

    try:
        resp = requests.patch(BASE_URL_CUP, json=payload, timeout=3)
        print(f"[CUP] PATCH -> Status: {resp.status_code}")
    except Exception as e:
        print(f"[CUP] Error: {e}")

def request_Liquid(data):
    uuid_val = data.get("uuid")
    weight = data.get("weight")
    liquid_type = data.get("type")

    if weight is None or weight <= 0:
        return

    url = f"{BASE_URL_LIQUID}/by-bin/{BIN_ID_DEFAULT}"
    payload = {
        "weight": weight,
        "uuid": uuid_val,
        "type": liquid_type
    }

    try:
        resp = requests.patch(url, json=payload, timeout=3)
        print(f"[LIQUID] PATCH -> Status: {resp.status_code}")
    except Exception as e:
        print(f"[LIQUID] Error: {e}")

def request_IR(data):
    # Sniff binId and uuid to help with laser data association
    uuid_val = data.get("uuid")
    bin_id = data.get("binId")
    
    if uuid_val and bin_id:
        # If we already have a buffer for this UUID, update the binId
        if uuid_val in laser_buffers:
            laser_buffers[uuid_val]['binId'] = bin_id
        else:
            # Create a new buffer entry with this binId
            laser_buffers[uuid_val] = {
                'timestamp': time.time(),
                'samples': [None] * MAX_SAMPLES,
                'received_count': 0,
                'binId': bin_id
            }

    try:
        resp = requests.post(BASE_URL_IR, json=data, timeout=3)
        print(f"[IR] SEND -> Status: {resp.status_code}")
    except Exception as e:
        print(f"[IR] Error: {e}")

def process_laser_fragment(data):
    uuid_val = data.get("uuid")
    idx = data.get("idx")
    fragment_data = data.get("data") # List of integers

    if not uuid_val or idx is None or not fragment_data:
        return

    # Initialize buffer if not exists
    if uuid_val not in laser_buffers:
        laser_buffers[uuid_val] = {
            'timestamp': time.time(),
            'samples': [None] * MAX_SAMPLES,
            'received_count': 0,
            'binId': BIN_ID_DEFAULT # Default, might be updated by IR event
        }

    buffer = laser_buffers[uuid_val]
    buffer['timestamp'] = time.time() # Update timestamp to keep alive

    # Fill samples
    for i, val in enumerate(fragment_data):
        target_idx = idx + i
        if target_idx < MAX_SAMPLES:
            if buffer['samples'][target_idx] is None:
                buffer['samples'][target_idx] = val
                buffer['received_count'] += 1

    # Check if complete (or sufficiently complete?)
    # For now, let's assume we need all 250 samples.
    # Or we can check if we received the last chunk?
    # Since we know MAX_SAMPLES is 250, we can check if received_count is close to 250.
    # But packets might be lost. We should probably have a timeout-based flush or a strict check.
    
    if buffer['received_count'] >= MAX_SAMPLES:
        # Reassemble and send
        finalize_laser_data(uuid_val)

def finalize_laser_data(uuid_val):
    if uuid_val not in laser_buffers:
        return

    buffer = laser_buffers[uuid_val]
    
    # Construct samples list with timeMsec
    formatted_samples = []
    for i, dist in enumerate(buffer['samples']):
        # If packet was lost, dist might be None. We can skip or interpolate.
        # For now, let's use 0 or skip.
        if dist is not None:
            formatted_samples.append({
                "distanceMm": dist,
                "timeMsec": i * 20 # Assuming 20ms interval
            })
    
    assembled_data = {
        "uuid": uuid_val,
        "binId": buffer['binId'],
        "samples": formatted_samples
    }

    request_Laser(assembled_data)
    
    # Remove from buffer
    del laser_buffers[uuid_val]

def cleanup_buffers():
    """Removes old incomplete buffers"""
    now = time.time()
    to_remove = []
    for uuid_val, buffer in laser_buffers.items():
        if now - buffer['timestamp'] > FRAGMENT_TIMEOUT:
            print(f"[WARN] Dropping incomplete laser data for UUID {uuid_val}. Received: {buffer['received_count']}/{MAX_SAMPLES}")
            # Optional: Send partial data?
            to_remove.append(uuid_val)
    
    for uuid_val in to_remove:
        del laser_buffers[uuid_val]

# --- Main Loop ---
print("\n" + "=" * 60)
print("Data Collector Started (Fragment Support)")
print("Waiting for data from STM32...")
print("=" * 60 + "\n")

full_buffer = ""

while True:
    time.sleep(0.01)
    
    # Periodic cleanup
    cleanup_buffers()

    if ser and ser.in_waiting > 0:
        try:
            chunk = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
            full_buffer += chunk

            while '\n' in full_buffer or '\r' in full_buffer:
                line_end = full_buffer.find('\n')
                if line_end == -1:
                    line_end = full_buffer.find('\r')

                line = full_buffer[:line_end].strip()
                full_buffer = full_buffer[line_end + 1:]

                if not line:
                    continue
                
                # Check for bracketed debug messages first (e.g. [#1]...)
                if line.startswith('[') and ']' in line:
                    # It might be "[#1] {...}"
                    # Try to find the JSON part
                    json_start = line.find('{')
                    if json_start != -1:
                        # Extract JSON
                        line = line[json_start:]

                # JSON Parsing
                if line.startswith('{') and '}' in line:
                    try:
                        # Find the last closing brace to handle cases like "OK {json}"
                        json_end = line.rindex('}') + 1
                        json_str = line[:json_end]
                        
                        data = json.loads(json_str)

                        # --- UUID Mapping Logic ---
                        # The TX might send 'id' instead of 'uuid'.
                        # We need to map short 'id' (e.g. "0001") to a full UUID for the server.
                        
                        short_id = data.get('id')
                        if short_id:
                            # If it's the special LIVE id, keep it as is
                            if short_id == "LIVE":
                                data['uuid'] = "LIVE"
                            else:
                                # Check if we need to generate a new UUID
                                # If this is a new IR event (beamBlocked=true), force a new UUID?
                                # Or just use existing mapping?
                                # Problem: If we reuse mapping forever, all events will have same UUID.
                                # Solution: If 'beamBlocked' is present (IR event), we assume it's the start of a new event.
                                # But we might receive multiple IR packets for same event.
                                # Let's generate a new UUID if 'id' is not in map, OR if it's an IR event start?
                                # Actually, simpler: If 'id' is not in map, generate one.
                                # We rely on the script being restarted or some timeout to clear old IDs?
                                # Better: If we see 'beamBlocked': true, we *could* refresh, but risk splitting event if multiple IRs trigger.
                                # Let's stick to: Create if missing.
                                
                                if short_id not in id_map:
                                    id_map[short_id] = str(uuid.uuid4())
                                    print(f"[INFO] New Event Detected. Mapped ID {short_id} -> {id_map[short_id]}")
                                
                                data['uuid'] = id_map[short_id]
                        
                        # Ensure 'uuid' key exists if 'id' was used
                        if 'uuid' not in data and 'id' in data:
                             data['uuid'] = data['id'] # Fallback

                        # --------------------------

                        # 1. Laser Fragment (has 'idx' and 'data')
                        if 'idx' in data and 'data' in data:
                            process_laser_fragment(data)
                        
                        # 2. Legacy Laser (full packet) - just in case
                        elif 'binWidthMm' in data:
                            # Convert to new format if needed or just pass
                            # But request_Laser expects our assembled format now.
                            # Let's adapt it quickly.
                            samples = data.get('samples', [])
                            assembled = {
                                "uuid": data.get("uuid", "UNKNOWN"),
                                "binId": data.get("binId", BIN_ID_DEFAULT),
                                "samples": samples
                            }
                            request_Laser(assembled)

                        # 3. Cup
                        elif 'type' in data and data['type'] == 'CUP':
                            request_Cup(data)

                        # 4. Liquid
                        elif 'type' in data and data['type'] == 'WATER':
                            request_Liquid(data)

                        # 5. Ultrasonic
                        elif 'distanceCm' in data:
                            request_sonic(data)

                        # 6. IR Event
                        elif 'beamBlocked' in data:
                            # If this is a new IR event, maybe we should force refresh the UUID?
                            # If we assume IR comes first, we can do:
                            # id_map[short_id] = str(uuid.uuid4())
                            # But let's be careful about duplicates.
                            # For now, let's just use the mapping logic above.
                            request_IR(data)

                    except json.JSONDecodeError:
                        # Not a JSON or incomplete
                        pass
                    except Exception as e:
                        print(f"[ERROR] Processing Error: {e}")
                else:
                    # Print non-JSON lines for debugging
                    if line:
                        print(f"[STM32] {line}")

        except Exception as e:
            print(f"[ERROR] Serial Read Error: {e}")
            full_buffer = ""
            continue
