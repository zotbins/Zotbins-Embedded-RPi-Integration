import logging

from sensors.weight_sensor import WeightSensor, default_calibration_path

log = logging.getLogger("Weight")


class Weight:
    def __init__(self, dout_pin, sck_pin, samples, calibration_id="zotbin-1"):
        self.samples = samples
        self.sensor = WeightSensor(
            dt_gpio=dout_pin,
            sck_gpio=sck_pin,
            gain=128,
            calibration_file=str(default_calibration_path(calibration_id)),
        )
        if self.sensor.scale == 0:
            log.warning("No calibration at %s; run weight_sensor.calibrate", self.sensor.calibration_file)

    def read_grams(self):
        """Returns grams, or None if the sensor couldn't be read."""
        try:
            return self.sensor.read_grams(samples=self.samples)
        except Exception as e:
            log.warning("Failed to read weight: %s", e)
            return None

    def close(self):
        self.sensor.close()
