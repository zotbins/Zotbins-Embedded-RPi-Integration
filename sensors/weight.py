from sensors.weight_sensor import WeightSensor, default_calibration_path
import time


def weight_process(input_queue, output_queue, dout_pin, sck_pin, samples):
    print("[Weight] Started")
    
    weight_sensor = _initialize_weight_sensor(dout_pin, sck_pin)
    
    try:
        while True:
            data = input_queue.get()
            weight = _measure_weight(weight_sensor, samples)
            data['weight'] = weight
            output_queue.put(data)
            print(f"[Weight] Weight: {weight:.2f} g")
            
    except KeyboardInterrupt:
        print("[Weight] Shutting down")


def _initialize_weight_sensor(dout_pin, sck_pin):
    try:
        cal_file = str(default_calibration_path("zotbin-1"))
        return WeightSensor(
            dt_gpio=dout_pin,
            sck_gpio=sck_pin,
            gain=128,
            use_pigpio=False,
            calibration_file=cal_file
        )
    except Exception as e:
        print(f"[Weight] Failed to initialize sensor: {e}")
        return None


def _measure_weight(weight_sensor, samples):
    if not weight_sensor:
        return 0.0
    
    try:
        return weight_sensor.read_grams(samples=samples)
    except Exception as e:
        print(f"[Weight] Failed to read weight: {e}")
        return 0.0