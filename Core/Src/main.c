/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2023 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the file 'LICENSE' in
  * the ST/SW4STM32 CubeMX directory.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "hx711.h"
#include <stdio.h>
#include <string.h>
#include <math.h>

#define WEIGHT_THERSHOU 10.0f    // 10g 이내면 안정
#define STABLE_COUNT     3        // 연속 안정 카운트
#define AVG_N            10       // 이동평균 창 길이

#define OBJECT_ON_THRESH   40.0f  // 이 이상이면 "물체 올라옴" 후보
#define OBJECT_OFF_THRESH  15.0f  // 이 이하로 떨어지면 "물체 내려감
/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */
// 이동평균 버퍼
static float avg_buf[AVG_N];
static int   avg_idx = 0;
static int   avg_filled = 0;
// 시퀀스(줄 번호)로 세션/출력 구분
static uint32_t seq = 0;

static int is_stable = 0;
static float stable_weight = 0.0f;
// === 함수 선언 ===
static void avg_reset(void);
static float avg_push(float v);
static int   is_saturated(int32_t raw);
/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
HX711_t hx;
UART_HandleTypeDef huart2;

/* USER CODE BEGIN PV */
// UUID
static uint32_t uuid_counter = 0;
static char current_event_uuid[37] = {0};
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_USART2_UART_Init(void);
/* USER CODE BEGIN PFP */
int __io_putchar(int ch)
{
	HAL_UART_Transmit(&huart2, (uint8_t *)&ch, 1, HAL_MAX_DELAY);
	return ch;
}

// UUID
void generate_uuid(char *uuid_str);
static int first_stable_sent = 0;    // 0: 아직 uuid 출력 안함, 1: 이미 출력함

// 평균 구하기
static void avg_reset(void) {
  for (int i = 0; i < AVG_N; i++) avg_buf[i] = 0.0f;
  avg_idx = 0;
  avg_filled = 0;
}

static float avg_push(float v) {
  avg_buf[avg_idx] = v;
  avg_idx = (avg_idx + 1) % AVG_N;
  if (avg_filled < AVG_N) avg_filled++;

  float s = 0.0f;
  for (int i = 0; i < avg_filled; i++) s += avg_buf[i];
  return s / (float)avg_filled;
}

static int is_saturated(int32_t raw) {
  return (raw == 8388607 || raw == -8388608); // HX711 포화값
}

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_USART2_UART_Init();
  /* USER CODE BEGIN 2 */
  /* HX711 모듈 초기화 (DOUT = PB4, SCK = PB5, gain=128) */
  HX711_Init(&hx,
			 GPIOB, GPIO_PIN_4, // DOUT (PB4)
			 GPIOB, GPIO_PIN_5, // SCK (PB5)
			 HX711_GAIN_128);

  // 안정화  시간
   HAL_Delay(500);

  // 빈 상태에서 영점 잡기
  hx.offset = HX711_Tare(&hx, 20);
  hx.scale = 11110.0f;

  avg_reset();
  seq = 0;

  printf("scale= %.2f\r\n", hx.scale);
  printf("offset= %ld\r\n", (long)hx.offset);

  // UUID
  uuid_counter = 0;
  memset(current_event_uuid, 0, sizeof(current_event_uuid));

  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  float prev = 0.0f;
  int   stable_cnt = 0;

  while (1) {

		// raw 읽기
		int32_t raw = HX711_ReadRaw(&hx);

		//  포화/이상치 버리기
		if (is_saturated(raw)) {
		// 포화는 그냥 무시
			HAL_Delay(50);
			continue;
		}

		// 무게 계산
		int32_t net = raw - hx.offset;
		float w = (hx.scale == 0.0f) ? 0.0f : (float)net / hx.scale;

		// 이동평균 (부팅/재Tare 이후엔 버퍼가 비워져 있어서 이전 샘플 영향 X)
		float w_filt = avg_push(w);

		// 안정구간 판정 (변화량 기준)
		if (fabsf(w_filt - prev) < WEIGHT_THERSHOU) {
			stable_cnt++;
		}
		else {
			stable_cnt = 0;
  	  	}
		prev = w_filt;


		// 항상 필터 값 로그 (디버깅용)
//		printf("#%lu w=%.2f g (filt)\r\n", ++seq, w_filt);

	 // ======= STABLE ON =======
		if (!is_stable && stable_cnt >= STABLE_COUNT) {
			is_stable = 1;
			stable_weight = w_filt;

			// 음수면 무시
			if (stable_weight <= 0.0f) {
				// 그냥 다음 루프
			} else {
				if (!first_stable_sent) {
					char uuid[40];
					generate_uuid(uuid);
					printf("{\"uuid\":\"%s\",\"weight\":%.2f}\r\n", uuid, stable_weight);
					first_stable_sent = 1;
				} else {
					printf("{\"weight\":%.2f}\r\n", stable_weight);
				}
			}
		}

		// ======= STABLE OFF =======
		if (is_stable && fabsf(w_filt - stable_weight) > WEIGHT_THERSHOU) {
			is_stable = 0;

			if (w_filt > 0.0f) {
				printf("{\"weight\":%.2f}\r\n", w_filt);
			}
		}

	/* USER CODE END WHILE */
		HAL_Delay(100);
  }
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE3);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;
  RCC_OscInitStruct.PLL.PLLM = 16;
  RCC_OscInitStruct.PLL.PLLN = 336;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV4;
  RCC_OscInitStruct.PLL.PLLQ = 2;
  RCC_OscInitStruct.PLL.PLLR = 2;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief USART2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART2_UART_Init(void)
{

  /* USER CODE BEGIN USART2_Init 0 */

  /* USER CODE END USART2_Init 0 */

  /* USER CODE BEGIN USART2_Init 1 */

  /* USER CODE END USART2_Init 1 */
  huart2.Instance = USART2;
  huart2.Init.BaudRate = 115200;
  huart2.Init.WordLength = UART_WORDLENGTH_8B;
  huart2.Init.StopBits = UART_STOPBITS_1;
  huart2.Init.Parity = UART_PARITY_NONE;
  huart2.Init.Mode = UART_MODE_TX_RX;
  huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart2.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart2) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART2_Init 2 */

  /* USER CODE END USART2_Init 2 */

}

// B1 버튼 누를 시 버퍼 비우기 및 영점 다시 잡기
// ------------------------------------------------------------------
// ** 변경된 부분: 버튼 콜백 로직을 비움 **
// ------------------------------------------------------------------
void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin)
{
	if (GPIO_Pin == B1_Pin) {
        // 기존 로직 제거됨. 버튼을 눌러도 영점 재조정이나 버퍼 초기화는 일어나지 않음.
	}
}


/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOH_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(LD2_GPIO_Port, LD2_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pin Output Level for SCK (PB5) */
  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_5, GPIO_PIN_RESET);

  /*Configure GPIO pin : B1_Pin */
  GPIO_InitStruct.Pin = B1_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_FALLING;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(B1_GPIO_Port, &GPIO_InitStruct);

  /*Configure GPIO pin : LD2_Pin */
  GPIO_InitStruct.Pin = LD2_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(LD2_GPIO_Port, &GPIO_InitStruct);

  /*Configure GPIO pin : PB5 (SCK) */
  GPIO_InitStruct.Pin = GPIO_PIN_5;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

  /*Configure GPIO pin : PB4 (DOUT) */
  GPIO_InitStruct.Pin = GPIO_PIN_4;
  GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */
// UUID
void generate_uuid(char *uuid_str) {
    uint32_t timestamp = HAL_GetTick();  // 시스템 가동 시간 (ms)
    uint32_t counter = uuid_counter++;

    uint32_t rand1 = (timestamp * 1103515245 + 12345) & 0x7FFFFFFF;
    uint32_t rand2 = (counter * 1664525 + 1013904223) & 0x7FFFFFFF;

    // xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    snprintf(uuid_str, 37, "%08lx-%04x-%04lx-%04lx-%08lx%04x",
        timestamp,                  // 8자리: 타임스탬프
        (uint16_t)(counter & 0xFFFF), // 4자리: 카운터
        (rand1 >> 16) & 0xFFFF,       // 4자리: 랜덤1
        rand2 & 0xFFFF,               // 4자리: 랜덤2
        rand1,                       // 8자리: 랜덤1 전체
        (uint16_t)(rand2 >> 16)       // 4자리: 랜덤2
    );
}
/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  * where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
