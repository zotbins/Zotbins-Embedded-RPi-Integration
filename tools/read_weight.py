import argparse

from weight_sensor import WeightSensor


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dt", type=int, default=5)
    p.add_argument("--sck", type=int, default=6)
    p.add_argument("--gain", type=int, default=128)
    p.add_argument("--samples", type=int, default=12)
    p.add_argument("--no-pigpio", action="store_true")
    args = p.parse_args()

    ws = WeightSensor(dt_gpio=args.dt, sck_gpio=args.sck, gain=args.gain, use_pigpio=not args.no_pigpio)
    try:
        grams = ws.read_grams(samples=args.samples)
        print(f"{grams:.2f}")
    finally:
        ws.close()


if __name__ == "__main__":
    main()