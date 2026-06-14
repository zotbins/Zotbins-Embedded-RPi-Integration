from sensors.weight_sensor import WeightSensor, default_calibration_path
from sensors.weight_sensor.errors import CalibrationError, HX711NotReadyError, HX711ReadError

_MAX_CONSECUTIVE_FAILURES = 10


def weight_process(input_queue, output_queue, dout_pin, sck_pin, samples, bin_id="zotbin-1"):
    print("[Weight] Started")

    weight_sensor = _initialize_weight_sensor(dout_pin, sck_pin, bin_id)
    consecutive_failures = 0

    try:
        while True:
            data = input_queue.get()

            if weight_sensor is None:
                weight_sensor = _initialize_weight_sensor(dout_pin, sck_pin, bin_id)
                if weight_sensor is None:
                    data['weight'] = None
                    output_queue.put(data)
                    continue
                consecutive_failures = 0

            weight = _measure_weight(weight_sensor, samples)

            if weight is None:
                consecutive_failures += 1
                if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                    print(f"[Weight] {_MAX_CONSECUTIVE_FAILURES} consecutive failures, reinitializing")
                    _safe_close(weight_sensor)
                    weight_sensor = None
                    consecutive_failures = 0
            else:
                consecutive_failures = 0
                print(f"[Weight] Weight: {weight:.2f} g")

            data['weight'] = weight
            output_queue.put(data)

    except KeyboardInterrupt:
        print("[Weight] Shutting down")
    finally:
        _safe_close(weight_sensor)


def _initialize_weight_sensor(dout_pin, sck_pin, bin_id):
    try:
        cal_file = str(default_calibration_path(bin_id))
        return WeightSensor(
            dt_gpio=dout_pin,
            sck_gpio=sck_pin,
            gain=128,
            calibration_file=cal_file,
        )
    except Exception as e:
        print(f"[Weight] Failed to initialize sensor: {e}")
        return None


def _measure_weight(weight_sensor, samples):
    if weight_sensor is None:
        return None
    try:
        return weight_sensor.read_grams(samples=samples)
    except (CalibrationError, HX711NotReadyError, HX711ReadError) as e:
        print(f"[Weight] Read error: {e}")
        return None
    except Exception as e:
        print(f"[Weight] Unexpected error: {e}")
        return None


def _safe_close(sensor):
    if sensor is not None:
        try:
            sensor.close()
        except Exception:
            pass