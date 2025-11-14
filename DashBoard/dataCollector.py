import serial
import requests
import json
import time

SERIAL_PORT = 'COM6'
BAUD_RATE   = 115200
SPRING_BASE_URL = 'http://localhost:8080/api/sensors/cups'
# BIN_ID = 2

def parse_json_line(line: str):
    """
    주어진 문자열 라인을 JSON 객체로 파싱
    """
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        # JSON 디코딩 오류 발생 시 None 반환
        return None
    except Exception:
        # 기타 예외 처리
        return None

def main():
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    print(f"Opened {SERIAL_PORT}")

    while True:
        try:
            raw = ser.readline()
            if not raw:
                continue

            # 바이트를 문자열로 디코딩하고 공백 제거
            line = raw.decode('utf-8', errors='ignore').strip()
            if not line:
                continue

            print("STM32:", line)

            # JSON 시작 여부 확인 (디버그 메시지 등 필터링)
            if not line.startswith("{"):
                continue

            data = parse_json_line(line)
            if not data:
                print("Error: Invalid JSON format received.")
                continue
            
            # JSON 데이터에서 "weight"를 추출
            weight = data.get("weight")

            # weight 필드가 없거나 0 이하인 경우 처리 방지
            if weight is None or weight <= 0:
                print(f"Skipping (weight <= 0 or missing): {weight}")
                continue

            # STM32에서 받은 데이터에 isLiquid = true 필드를 추가하여 payload 구성
            data['isLiquid'] = True 
            payload = data # 이제 payload는 {"weight": X, "isLiquid": true} 형태

            url = SPRING_BASE_URL
            
            # 물통 무게 업데이트
            # STM32에서 받은 JSON 데이터 (data)를 그대로 payload로 사용
            resp = requests.patch(url, json=payload, timeout=3)
            print(f"PATCH -> Status Code: {resp.status_code}")

        except KeyboardInterrupt:
            print("\nExiting program...")
            break
        except serial.SerialException as e:
            print(f"Serial Error: {e}. Reconnecting in 5 seconds...")
            ser.close()
            time.sleep(5)
            try:
                ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
                print(f"Reopened {SERIAL_PORT}")
            except serial.SerialException:
                print("Failed to reopen serial port.")
        except requests.exceptions.RequestException as e:
            print(f"HTTP Request Error: {e}")
            time.sleep(1)
        except Exception as e:
            print("General Error:", e)
            time.sleep(1)

if __name__ == "__main__":
    main()