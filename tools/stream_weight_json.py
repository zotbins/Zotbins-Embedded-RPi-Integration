import argparse
import json
import time

from weight_sensor import WeightSensor


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dt", type=int, default=5)
    p.add_argument("--sck", type=int, default=6)
    p.add_argument("--gain", type=int, default=128)
    p.add_argument("--samples", type=int, default=10)
    p.add_argument("--hz", type=float, default=2.0)
    p.add_argument("--bin-id", type=str, default="zotbin-unknown")
    p.add_argument("--no-pigpio", action="store_true")
    args = p.parse_args()

    ws = WeightSensor(dt_gpio=args.dt, sck_gpio=args.sck, gain=args.gain, use_pigpio=not args.no_pigpio)
    period = 1.0 / max(args.hz, 0.1)

    try:
        while True:
            grams = ws.read_grams(samples=args.samples)
            msg = {
                "bin_id": args.bin_id,
                "ts": int(time.time()),
                "weight_grams": round(float(grams), 3),
            }
            print(json.dumps(msg), flush=True)
            time.sleep(period)
    except KeyboardInterrupt:
        return
    finally:
        ws.close()


if __name__ == "__main__":
    main()