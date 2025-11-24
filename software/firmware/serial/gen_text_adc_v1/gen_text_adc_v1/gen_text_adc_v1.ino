#include <Ticker.h>
#include "Keyboard.h"
#include "utils_gen_text_adc_v1.h"
#include <tuple>

#define SHOW_LINES_SERIALPLOT

#pragma region global_functions_variables
  constexpr float raw2volt(float dat);
  volatile auto data_raw=0.0, itemp=0.0;
  //TIME
  Ticker ADC_GET;

  void func_get_adc(){
    data_raw = raw2volt(analogRead(A0));
    itemp = itemp2cal(analogReadTemp());
  }

  std::tuple<float, float> sensors(){
    float noise=data_raw;
    float temp=itemp;

    return {noise, temp};
  };
#pragma endregion

/*********************************************/
void setup() {
  Serial.begin(9600);
  analogReadResolution(12);
  ADC_GET.attach_ms(1, func_get_adc);
  Keyboard.begin();

}

void loop() { 
  auto [noise, temp] = sensors();
#ifdef SHOW_LINES_SERIALPLOT
  Serial.print("3.3,");
  Serial.print(noise);
  Serial.print(",0,");
  Serial.print(temp);
  Serial.print("\n");
#endif
  
  if(noise>1.2f){
    Keyboard.println("Hello world from a RP2350!");
    delay(50);
  }
}
/*************************************************/

