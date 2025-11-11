#include "hx711.h"
#include <math.h> // fabs() 함수 사용을 위해 포함 (main.c에서 사용됨)

// SCK 핀을 낮춤 (RESET)
#define HX711_SCK_LOW(handle)   HAL_GPIO_WritePin(handle->SCK_Port, handle->SCK_Pin, GPIO_PIN_RESET)
// SCK 핀을 높임 (SET)
#define HX711_SCK_HIGH(handle)  HAL_GPIO_WritePin(handle->SCK_Port, handle->SCK_Pin, GPIO_PIN_SET)
// DT 핀의 상태를 읽음
#define HX711_DT_READ(handle)   HAL_GPIO_ReadPin(handle->DT_Port, handle->DT_Pin)

// 타이밍 문제 해결을 위한 최소 지연 함수
static inline void HX711_Delay_us(uint32_t us) {
    for (volatile uint32_t i = 0; i < (us * 10); i++) { __NOP(); }
}

void HX711_Init(HX711_Handle* hx711, GPIO_TypeDef* sckPort, uint16_t sckPin, GPIO_TypeDef* dtPort, uint16_t dtPin) {
    hx711->SCK_Port = sckPort;
    hx711->SCK_Pin = sckPin;
    hx711->DT_Port = dtPort;
    hx711->DT_Pin = dtPin;
    hx711->offset = 0;
    hx711->scale = 1.0f;
    HX711_SCK_LOW(hx711);
}

void HX711_WaitUntilReady(HX711_Handle* hx711) {
    uint32_t timeout = HAL_GetTick() + 1000;
    while (HX711_DT_READ(hx711) == GPIO_PIN_SET) {
        if (HAL_GetTick() >= timeout) {
            break;
        }
    }
}

long HX711_Read(HX711_Handle* hx711) {
    long data = 0;

    HX711_WaitUntilReady(hx711);

    for (int i = 0; i < 24; i++) {
        HX711_SCK_HIGH(hx711);
        HX711_Delay_us(1);

        data = data << 1;

        HX711_SCK_LOW(hx711);
        HX711_Delay_us(1);

        if (HX711_DT_READ(hx711) == GPIO_PIN_SET) {
            data++;
        }
    }

    HX711_SCK_HIGH(hx711);
    HX711_SCK_LOW(hx711);

    if (data & 0x800000) {
        data |= (long)0xFF000000;
    }

    return data;
}

long HX711_Read_Average(HX711_Handle* hx711, uint8_t times) {
    long sum = 0;
    for (uint8_t i = 0; i < times; i++) {
        sum += HX711_Read(hx711);
    }
    return sum / times;
}

void HX711_Set_Scale(HX711_Handle* hx711, float scale) {
    hx711->scale = scale;
}

void HX711_Tare(HX711_Handle* hx711, uint8_t times) {
    hx711->offset = HX711_Read_Average(hx711, times);
}

float HX711_Get_Value(HX711_Handle* hx711, uint8_t times) {
    long raw_data = HX711_Read_Average(hx711, times);
    return (float)(raw_data - hx711->offset) / hx711->scale;
}
