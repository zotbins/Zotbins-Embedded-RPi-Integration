import argparse
import json
import time

from weight_sensor import CalibrationError, HX711NotReadyError, HX711ReadError, WeightSensor, default_calibration_path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--dt", type=int, default=5)
    p.add_argument("--sck", type=int, default=6)
    p.add_argument("--gain", type=int, default=128)
    p.add_argument("--samples", type=int, default=12)
    p.add_argument("--hz", type=float, default=2.0)
    p.add_argument("--bin-id", type=str, default="zotbin-1")
    p.add_argument("--calibration-file", type=str, default=None)
    p.add_argument("--no-pigpio", action="store_true")
    p.add_argument("--raw", action="store_true")
    p.add_argument("--include-raw", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    cal_file = args.calibration_file or str(default_calibration_path(args.bin_id))
    ws = WeightSensor(dt_gpio=args.dt, sck_gpio=args.sck, gain=args.gain, use_pigpio=not args.no_pigpio, calibration_file=cal_file)
    period = 1.0 / max(args.hz, 0.1)

    boot = {
        "status": "boot",
        "bin_id": args.bin_id,
        "dt": args.dt,
        "sck": args.sck,
        "gain": args.gain,
        "samples": args.samples,
        "hz": args.hz,
        "use_pigpio": (not args.no_pigpio),
        "calibration_file": str(ws.calibration_file),
        "offset": ws.offset,
        "scale": ws.scale,
        "cal_updated_at": int(ws.cal.updated_at),
        "ts": time.time(),
    }
    print(json.dumps(boot), flush=True)

    try:
        next_t = time.monotonic()
        while True:
            ts = time.time()
            try:
                if args.raw:
                    raw = ws.read_raw_avg(samples=args.samples, settle_ms=2)
                    out = {"status": "ok", "bin_id": args.bin_id, "ts": ts, "raw": raw}
                else:
                    grams = ws.read_grams(samples=args.samples)
                    out = {"status": "ok", "bin_id": args.bin_id, "ts": ts, "weight_grams": grams}
                    if args.include_raw:
                        out["raw"] = ws.read_raw_avg(samples=max(3, min(args.samples, 8)), settle_ms=0)
                print(json.dumps(out), flush=True)
            except (HX711NotReadyError, HX711ReadError) as e:
                print(json.dumps({"status": "not_ready", "bin_id": args.bin_id, "ts": ts, "error": str(e)}), flush=True)
            except CalibrationError as e:
                print(json.dumps({"status": "not_calibrated", "bin_id": args.bin_id, "ts": ts, "error": str(e)}), flush=True)

            next_t += period
            sleep_s = next_t - time.monotonic()
            if sleep_s < 0:
                next_t = time.monotonic()
                sleep_s = period
            time.sleep(sleep_s)
    finally:
        ws.close()


if __name__ == "__main__":
    raise SystemExit(main())