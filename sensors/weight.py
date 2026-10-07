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


if __name__ == "__main__":
    # Standalone test: python -m sensors.weight [--dout N] [--sck N] [--samples N] [--interval S]
    # To calibrate: cd sensors && python -m weight_sensor.calibrate --bin-id zotbin-1
    import argparse
    import time

    from config import CONFIG

    parser = argparse.ArgumentParser(description="Print the measured weight repeatedly.")
    parser.add_argument("--dout", type=int, default=CONFIG["weight_dout_pin"])
    parser.add_argument("--sck", type=int, default=CONFIG["weight_sck_pin"])
    parser.add_argument("--samples", type=int, default=CONFIG["weight_samples"])
    parser.add_argument("--interval", type=float, default=0.5, help="seconds between readings")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S")

    weight = Weight(args.dout, args.sck, args.samples)
    print(f"DOUT={args.dout} SCK={args.sck}, calibration {weight.sensor.calibration_file}. Ctrl+C to quit.")
    try:
        while True:
            grams = weight.read_grams()
            print("read failed" if grams is None else f"{grams:8.1f} g")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        weight.close()
