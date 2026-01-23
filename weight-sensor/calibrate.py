import argparse
import sys
import time

from .weight import WeightSensor


def _pause(msg: str, seconds: float = 1.0):
    print(msg, flush=True)
    time.sleep(seconds)


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dt", type=int, default=5)
    p.add_argument("--sck", type=int, default=6)
    p.add_argument("--gain", type=int, default=128)
    p.add_argument("--no-pigpio", action="store_true")
    p.add_argument("--known-grams", type=float, default=None)
    args = p.parse_args(argv)

    ws = WeightSensor(dt_gpio=args.dt, sck_gpio=args.sck, gain=args.gain, use_pigpio=not args.no_pigpio)
    try:
        _pause("Warmup: reading sensor for a few seconds...")
        for _ in range(15):
            ws.read_raw_avg(samples=2)
            time.sleep(0.1)

        input("Remove all weight. Press Enter to tare...")
        ws.tare(samples=25)
        print(f"Tare complete. offset={ws.offset:.2f}")

        known = args.known_grams
        if known is None:
            known = float(input("Place a known weight (grams). Enter grams: ").strip())

        input(f"Place {known}g on the platform. Press Enter to continue...")
        ws.calibrate_with_known_weight(known_grams=known, samples=40)
        print(f"Calibration complete. scale={ws.scale:.6f} raw/g")

        input("Remove weight. Press Enter to do a quick check...")
        g0 = ws.read_grams(samples=15)
        print(f"Empty reading: {g0:.2f} g")

        return 0
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    finally:
        ws.close()


if __name__ == "__main__":
    raise SystemExit(main())