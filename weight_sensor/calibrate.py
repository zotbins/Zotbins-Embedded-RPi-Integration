import argparse
import time

from .errors import CalibrationError, HX711NotReadyError, HX711ReadError
from .weight import WeightSensor, default_calibration_path


def _read_stable_window(ws: WeightSensor, samples: int, settle_ms: int):
    vals = ws.read_raw_samples(target=samples, max_attempts=max(samples * 10, 200), settle_ms=settle_ms)
    vmin = min(vals)
    vmax = max(vals)
    return {"avg": sum(vals) / len(vals), "span": float(vmax - vmin), "min": float(vmin), "max": float(vmax)}


def _wait_for_stability(
    ws: WeightSensor,
    window_samples: int,
    span_raw: float,
    settle_ms: int,
    timeout_s: float,
):
    start = time.monotonic()
    last = None
    while time.monotonic() - start < timeout_s:
        last = _read_stable_window(ws, samples=window_samples, settle_ms=settle_ms)
        if last["span"] <= float(span_raw):
            return last
        time.sleep(0.2)
    raise CalibrationError(f"Signal not stable (span_raw={last['span'] if last else 'n/a'})")


def _warmup(ws: WeightSensor, attempts: int, settle_ms: int):
    ok = 0
    last_err = None
    for _ in range(attempts):
        try:
            ws.read_raw_avg(samples=5, settle_ms=settle_ms)
            ok += 1
        except (HX711NotReadyError, HX711ReadError) as e:
            last_err = e
        time.sleep(0.05)
    if ok == 0:
        raise HX711NotReadyError(str(last_err) if last_err else "No successful reads during warmup")


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dt", type=int, default=5)
    p.add_argument("--sck", type=int, default=6)
    p.add_argument("--gain", type=int, default=128)
    p.add_argument("--samples", type=int, default=40)
    p.add_argument("--known-grams", type=float, default=None)
    p.add_argument("--min-delta-raw", type=float, default=5000.0)
    p.add_argument("--bin-id", type=str, default="zotbin-1")
    p.add_argument("--calibration-file", type=str, default=None)
    p.add_argument("--stable-window-samples", type=int, default=30)
    p.add_argument("--stable-span-raw", type=float, default=1500.0)
    p.add_argument("--stable-timeout-s", type=float, default=12.0)
    p.add_argument("--no-pigpio", action="store_true")
    args = p.parse_args(argv)

    cal_file = args.calibration_file or str(default_calibration_path(args.bin_id))
    ws = WeightSensor(dt_gpio=args.dt, sck_gpio=args.sck, gain=args.gain, use_pigpio=not args.no_pigpio, calibration_file=cal_file)

    try:
        _warmup(ws, attempts=40, settle_ms=5)

        input("Remove all weight. Press Enter to tare...")
        _wait_for_stability(
            ws,
            window_samples=args.stable_window_samples,
            span_raw=args.stable_span_raw,
            settle_ms=5,
            timeout_s=args.stable_timeout_s,
        )
        ws.tare(samples=max(25, args.stable_window_samples))
        print(f"Tare complete. offset={ws.offset:.2f} cal_file={ws.calibration_file}")

        known = args.known_grams
        if known is None:
            known = float(input("Place a known weight (grams). Enter grams: ").strip())
        if not (known > 0):
            raise CalibrationError("known_grams must be > 0")

        input(f"Place {known}g on the platform. Press Enter to continue...")
        _wait_for_stability(
            ws,
            window_samples=args.stable_window_samples,
            span_raw=args.stable_span_raw,
            settle_ms=5,
            timeout_s=args.stable_timeout_s,
        )
        ws.calibrate_with_known_weight(known_grams=known, samples=args.samples, min_delta_raw=args.min_delta_raw)
        print(f"Calibration complete. scale={ws.scale:.6f} raw/g updated_at={ws.cal.updated_at}")

        input("Remove weight. Press Enter to do a quick check...")
        _wait_for_stability(
            ws,
            window_samples=args.stable_window_samples,
            span_raw=args.stable_span_raw,
            settle_ms=5,
            timeout_s=args.stable_timeout_s,
        )
        g0 = ws.read_grams(samples=25)
        print(f"Empty reading: {g0:.2f} g")

        return 0
    except (CalibrationError, HX711NotReadyError, HX711ReadError) as e:
        print(f"{type(e).__name__}: {e}")
        return 2
    finally:
        ws.close()


if __name__ == "__main__":
    raise SystemExit(main())