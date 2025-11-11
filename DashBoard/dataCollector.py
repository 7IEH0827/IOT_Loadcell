import serial
import requests
import json
import time

SERIAL_PORT = 'COM6'  
BAUD_RATE   = 115200

# Spring 서버 엔드포인트
SPRING_BASE_URL = 'http://localhost:8080/api/sensors/cups'

def parse_line(line: str) -> dict:
    """
    예시:
      "weight=123.45,liquid_detected=true" 같은 문자열을 dict로 변환
    """
    data = {}
    try:
        parts = line.split(',')
        for p in parts:
            if '=' not in p:
                continue
            k, v = p.split('=', 1)
            k = k.strip()
            v = v.strip()
            if not k:
                continue

            # 숫자 형태면 float/int로 변환
            if v.replace('.', '', 1).isdigit():
                if '.' in v:
                    data[k] = float(v)
                else:
                    data[k] = int(v)
            else:
                data[k] = v # 문자열 값은 그대로 유지 (예: 'true', 'false')
    except Exception as e:
        print("parse error:", e, "line:", line)
    return data

def main():
    # 시리얼 포트 열기
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        print(f"Opened serial port {SERIAL_PORT} @ {BAUD_RATE}")
    except serial.SerialException as e:
        print(f"Error opening serial port {SERIAL_PORT}: {e}")
        return

    while True:
        try:
            raw = ser.readline()  # '\n' 기준 한 줄 읽기
            if not raw:
                continue

            line = raw.decode('utf-8', errors='ignore').strip()
            if not line:
                continue

            print("from STM32:", line)

            payload = parse_line(line)
            if not payload:
                continue

            if "weight" not in payload:
                print("payload에 weight 값이 없음:", payload)
                continue

            weight_value = payload["weight"]
            
            # isliquid 값 계산
            liquid_status_str = payload.get("liquid_detected", "false").lower()
            isliquid_value = liquid_status_str == 'true'

            # PATCH /api/sensors/cups
            url = SPRING_BASE_URL 
            
            # JSON body 구조
            body = {
                "weight": weight_value,
                "isliquid": isliquid_value
            }
            
            print(f"To Spring: {json.dumps(body)}")

            resp = requests.patch(
                url,
                json=body,        # JSON 인코딩 및 Content-Type 설정
                timeout=3
            )

            print(f"PATCH {url} -> {resp.status_code}")
            # print(resp.text) # 디버깅용

        except KeyboardInterrupt:
            print("Exit by user")
            break
        except requests.exceptions.ConnectionError:
            print("Error: Spring Server 연결 실패 (localhost:8080)")
            time.sleep(3)
        except Exception as e:
            print("Error:", e)
            time.sleep(1)

if __name__ == "__main__":
    main()
