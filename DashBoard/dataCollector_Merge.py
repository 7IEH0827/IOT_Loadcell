import json
import time
import requests
import serial.tools.list_ports

ports = serial.tools.list_ports.comports()

print("=== Available COM Ports ===")
for port in ports:
    print(f"Port: {port.device}")
    print(f"Description: {port.description}")
    print(f"HWID: {port.hwid}")
    print("---------------------------")

flag = False
# config COM port
while True:
    time.sleep(0.1)
    portName = input("Enter the port name (or 'test' for test mode): ")
    if portName == "test":
        flag = True
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

BASE_URL_LASER = "http://localhost:8080/api/sensor/laser"
BASE_URL_LIQUID = 'http://localhost:8080/api/sensors/weight/liquids'
BASE_URL_CUP = 'http://localhost:8080/api/sensor/cup'
BASE_URL_SONIC = "http://localhost:8080/api/sensor/ultrasonic"
BASE_URL_IR = "http://localhost:8080/api/sensor/ir/events"

BIN_ID = 2
UUID_TO_SEND = None
LIVE_UUID = "LIVE"   # 실시간 채움률용 고정 UUID 
TIMEOUT   = 1

def request_Laser(data):
    try:
        print("\n" + "=" * 60)
        print("Sending data to server...")
        print(f"URL: {BASE_URL_LASER}/insertion-event")
        print(f"Samples: {len(data['samples'])} measurements")

        response = requests.post(
            f"{BASE_URL_LASER}/insertion-event",
            json=data,
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
                print(f"Event ID: {res_data.get('eventId')}")
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
    bin_id = data.get("binId", 1)
    dist_cm    = data.get("distanceCm")
    fill_rate  = data.get("fillRate")
    event_uuid = data.get("uuid")   # 이벤트면 여기에 값이 들어옴

    if dist_cm is None or fill_rate is None:
        print("[WARN] JSON missing distanceCm/fillRate:", data)
        return

    # 이벤트가 아니면 uuid를 LIVE로 고정
    uuid = event_uuid if event_uuid else LIVE_UUID

    payload = {
        "binId":      bin_id,
        "uuid":       uuid,
        "distanceCm": dist_cm,
        "fillRate":   fill_rate,
    }
    
    """
    payload 예:
    {
        "binId": 1,
        "uuid": "LIVE" or "550e8400-...",
        "distanceCm": 30.3,
        "fillRate": 60.6
    }
    """

    try:
        print("\n" + "=" * 60)
        print("Sending data to server...")
        print(f"URL: {BASE_URL_SONIC}")
        print("Payload:", payload)

        resp = requests.post(
            BASE_URL_SONIC,
            json=data,
            headers={"Content-Type": "application/json"},
            timeout=5,
        )

        print(f"[HTTP] Status: {resp.status_code}")
        try:
            js = resp.json()
            print("[HTTP] Response JSON:", js)
        except Exception:
            print("[HTTP] Response Text:", resp.text)

        print("=" * 60 + "\n")

    except requests.exceptions.ConnectionError:
        print(f"[ERROR] Connection failed: Server not running at {BASE_URL_SONIC}")
    except requests.exceptions.Timeout:
        print("[ERROR] Request timeout")
    except Exception as e:
        print("[ERROR]", e)

def request_Cup(data):
    if "uuid" in data:
        global UUID_TO_SEND
        UUID_TO_SEND = data.get("uuid")

    # JSON 데이터에서 컵의 "weight"를 추출
    weight = data.get("weight_cup")

    # weight 필드가 없거나 0 이하인 경우 처리 방지
    if weight is None or weight <= 0:
        print(f"Skipping (weight <= 0 or missing): {weight}")
        return

    url = BASE_URL_CUP
            
    payload = {
        "uuid": UUID_TO_SEND,
        "binId": BIN_ID,
        "weight": weight
    }

    # STM32에서 받은 JSON 데이터 (data)를 그대로 payload로 사용
    resp = requests.patch(url, json=payload, timeout=3)
    print(f"PATCH -> Status Code: {resp.status_code}")

def request_Liquid(data):
    weight = data.get("weight_liquid")
    if weight <= 0:
        return 0

    url = f"{BASE_URL_LIQUID}/by-bin/{BIN_ID}"

    # 물통 무게 업데이트
    resp = requests.patch(url, json=data, timeout=3)
    print("PATCH ->", resp.status_code)

def request_IR(data):
    resp = requests.post(BASE_URL_IR, json=data, timeout=3)
    print("[SEND]", resp.status_code, resp.text)

# 메인
print("\n" + "=" * 60)
print("Data Collector Started")
print("Waiting for data from STM32...")
print("=" * 60 + "\n")

full_buffer = ""

while True:
    time.sleep(0.01)

    if ser.in_waiting > 0:
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

                # JSON 파싱
                if line.startswith('{') and '}' in line:
                    json_start = line.index('{')
                    json_end = line.rindex('}') + 1
                    json_str = line[json_start:json_end]

                    try:
                        data = json.loads(json_str)

                        # 레이저 센서 값일 경우
                        if 'binWidthMm' in data:
                            request_Laser(data)

                        # 로드셀(컵) 센서 값일 경우
                        if 'weight_cup' in data:
                            request_Cup(data)

                        # 로드셀(물통) 센서 값일 경우
                        if 'weight_liquid' in data:
                            request_Liquid(data)

                        # 초음파 센서 값일 경우
                        if 'distanceCm' in data:
                            request_sonic(data)

                        # IR 센서 값일 경우
                        if 'beamBlocked' in data:
                            request_IR(data)

                    except json.JSONDecodeError as e:
                        print(f"[ERROR] JSON Parse Error: {e}")
                        print(f"JSON string: {json_str[:200]}...")
                else:
                    if line and not line.startswith('{'):
                        print(f"[STM32] {line}")

        except Exception as e:
            print(f"[ERROR] Read error: {e}")
            full_buffer = ""  # 에러 시 버퍼 초기화
            continue