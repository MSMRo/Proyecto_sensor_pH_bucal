

constexpr float raw2volt(float dat){
  float volt = (dat/4095.0)*3.3;

  return volt;
};

constexpr float itemp2cal(float dat){
  const float a = 1.000;   // ≈1 si solo corriges offset
  const float b = -1.50;   // ejemplo: compensar -1.5 °C
  float t_corr = a * dat + b;

  return t_corr;
};