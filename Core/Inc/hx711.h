#ifndef __HX711_H
#define __HX711_H
#include "stm32f4xx_hal.h"

// GPIO 핀 정의는 main.c 또는 여기에 포함된 헤더 파일에 맞게 조정
#define HX711_SCK_GPIO_Port GPIOB
#define HX711_SCK_Pin GPIO_PIN_10
#define HX711_DT_GPIO_Port GPIOB
#define HX711_DT_Pin GPIO_PIN_11

typedef struct {
    GPIO_TypeDef* SCK_Port;
    uint16_t SCK_Pin;
    GPIO_TypeDef* DT_Port;
    uint16_t DT_Pin;
    long offset;
    float scale;
} HX711_Handle;

// 모든 필요한 함수 선언: Init, Read, Read_Average, Tare, Set_Scale, Get_Value
void HX711_Init(HX711_Handle* hx711, GPIO_TypeDef* sckPort, uint16_t sckPin, GPIO_TypeDef* dtPort, uint16_t dtPin);
long HX711_Read(HX711_Handle* hx711);
long HX711_Read_Average(HX711_Handle* hx711, uint8_t times);
void HX711_Tare(HX711_Handle* hx711, uint8_t times);
void HX711_Set_Scale(HX711_Handle* hx711, float scale);
float HX711_Get_Value(HX711_Handle* hx711, uint8_t times);

#endif
