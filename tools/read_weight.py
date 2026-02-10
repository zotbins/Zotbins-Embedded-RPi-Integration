import argparse
import json
import time

from weight_sensor import CalibrationError, HX711NotReadyError, HX711ReadError, WeightSensor, default_calibration_path


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dt", type=int, default=5)
    p.add_argument("--sck", type=int, default=6)
    p.add_argument("--gain", type=int, default=128)
    p.add_argument("--samples", type=int, default=12)
    p.add_argument("--bin-id", type=str, default="zotbin-1")
    p.add_argument("--calibration-file", type=str, default=None)
    p.add_argument("--no-pigpio", action="store_true")
    p.add_argument("--raw", action="store_true")
    args = p.parse_args(argv)

    cal_file = args.calibration_file or str(default_calibration_path(args.bin_id))
    ws = WeightSensor(dt_gpio=args.dt, sck_gpio=args.sck, gain=args.gain, use_pigpio=not args.no_pigpio, calibration_file=cal_file)
    try:
        if args.raw:
            raw = ws.read_raw_avg(samples=args.samples, settle_ms=2)
            print(json.dumps({"ts": time.time(), "status": "ok", "bin_id": args.bin_id, "raw": raw}), flush=True)
            return 0

        grams = ws.read_grams(samples=args.samples)
        print(
            json.dumps(
                {
                    "ts": time.time(),
                    "status": "ok",
                    "bin_id": args.bin_id,
                    "weight_grams": grams,
                    "offset": ws.offset,
                    "scale": ws.scale,
                    "calibration_file": str(ws.calibration_file),
                }
            ),
            flush=True,
        )
        return 0
    except (HX711NotReadyError, HX711ReadError) as e:
        print(json.dumps({"ts": time.time(), "status": "not_ready", "bin_id": args.bin_id, "error": str(e)}), flush=True)
        return 3
    except CalibrationError as e:
        print(json.dumps({"ts": time.time(), "status": "not_calibrated", "bin_id": args.bin_id, "error": str(e)}), flush=True)
        return 4
    finally:
        ws.close()


if __name__ == "__main__":
    raise SystemExit(main())