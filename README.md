# Zotbins Raspberry PI Integration

## Program Description
Runs on a Raspberry Pi 3 or 4 as two processes:

- **IR watcher** (own process): checks the beam level every 10 ms and sends a trigger when it changes. By default that's when it goes clear (the lid opens); set `ir_trigger_on` to `"broken"` in `config.py` for the opposite.
- **Pipeline** (main process), once per trigger:
  Camera (detect object passing in the top two-thirds of the view, keep the frame where it looks biggest) -> wait for the trash to settle -> Ultrasonic (fullness) and Weight -> save to spool. Each reading has its own settle time in `config.py` (`ultrasonic_settle_time`, `weight_settle_time`), counted from when the object leaves the frame.
- **Uploader** (background thread): sends spooled records to the API oldest first. If the network is down, they stay on disk and are retried every 10 s.

Records are saved in `data/spool/` as `<timestamp>.jpg` + `<timestamp>.json`. Records the API refuses (4xx) are moved to `data/spool/rejected/`. The oldest are deleted past `max_records`.

All settings (pins, timings, API URL) are in `config.py`.

### Disabling Sensors
Set `enable_ir`, `enable_camera`, `enable_ultrasonic` or `enable_weight` to `False` in `config.py` to skip a sensor that isn't connected. The rest of the flow still runs, and the missing reading is stored as `null`:
- **Weight off:** weight isn't read. The ultrasonic still waits its own settle time.
- **Camera off:** each IR trigger still produces a record, without an image.
- **IR off:** the camera's motion detection starts each cycle.
- **IR and camera off:** a cycle runs every `no_trigger_interval` seconds.

## How to Run
Requires Raspberry Pi OS (Bookworm recommended) on a Pi 3 or 4.
```
git clone https://github.com/zotbins/Zotbins-Embedded-RPi-Integration.git
cd Zotbins-Embedded-RPi-Integration
```
Install the system packages (camera, OpenCV and GPIO libraries come from apt, not pip):
```
sudo apt install python3-picamera2 python3-opencv python3-numpy python3-pigpio pigpiod python3-rpi.gpio
sudo systemctl enable --now pigpiod
```
Create the virtual environment (it must see the apt packages) and install the rest:
```
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements.txt
```
In order to use the camera/GPIOs the RaspberryPi needs to have permission:
```
sudo usermod -aG gpio $USER
sudo usermod -aG video $USER
```
Calibrate the weight sensor (saved to `~/.config/weight_sensor/zotbin-1.json`):
```
cd sensors && python -m weight_sensor.calibrate --bin-id zotbin-1 && cd ..
```
Run:
```
python main.py
```

## Testing Sensors Individually
Run these from the project root (with the venv active). Pins default to `config.py`; override them with flags (`--help` lists them). Stop any running `zotbins` service first so it isn't using the pins.
```
python -m sensors.ir_sensor                 # prints a line each time it triggers (beam goes clear = lid opens)
python -m sensors.ir_sensor --debounce 0    # every trigger, no 3s lockout
python -m sensors.ir_sensor --state         # print clear/BROKEN every 0.2s (for wiring and alignment)
python -m sensors.ultrasonic                # prints distance (cm) every 0.5s
python -m sensors.weight                    # prints weight (g) every 0.5s
python -m sensors.camera                    # press Enter, pass an object, saves the picked frame to data/camera_test/
python -m sensors.camera --min-area 40      # try a different motion sensitivity
python -m sensors.camera --delay 3 --exposure 8000   # try a different exposure (us) before changing config.py
python -m sensors.camera --delay 5          # take one picture after 5s (no motion detection)
python -m sensors.camera --delay 5 --count 0   # a picture every 5s until Ctrl+C
```

## Run at Boot (systemd)
```
sed "s|@USER@|$USER|g; s|@DIR@|$PWD|g" deploy/zotbins.service | sudo tee /etc/systemd/system/zotbins.service
sudo systemctl daemon-reload
sudo systemctl enable --now zotbins
journalctl -u zotbins -f    # view logs
```

## Local Dashboard
The dashboard ([zotbins-data-visualizer](https://github.com/zotbins/zotbins-data-visualizer), a separate repo) can run on the Pi and show this bin's own records, without the cloud. `data/local_api.py` answers the dashboard's API requests (`/raw_data`, `/inferences`, `/waste-classes`) from `data/spool/` and `data/history/`, and serves the images. There is no ML on the Pi, so the composition charts stay empty.

Fullness is reported as a fraction using `bin_empty_distance_cm` and `bin_full_distance_cm` in `config.py`. Uploaded records are moved to `data/history/` (up to `max_history`) instead of being deleted, so the dashboard keeps them.

1. Start the local API (it only listens on the Pi itself):
   ```
   python -m data.local_api
   ```
2. In the dashboard repo (cloned separately, needs Node.js 20.9+), set `.env.local` to `NEXT_PUBLIC_API_URL=http://localhost:8000`, then:
   ```
   npm ci
   npm run build
   npx next start -p 9999
   ```
3. Open `http://<pi-address>:9999` from any computer on the network or Tailscale. It refreshes every 10 s.

To start both at boot (run from this repo; `DASHBOARD_DIR` is where the dashboard is cloned):
```
DASHBOARD_DIR=~/zotbins-data-visualizer
sed "s|@USER@|$USER|g; s|@DIR@|$PWD|g" deploy/zotbins-local-api.service | sudo tee /etc/systemd/system/zotbins-local-api.service
sed "s|@USER@|$USER|g; s|@DASHBOARD_DIR@|$DASHBOARD_DIR|g" deploy/zotbins-dashboard.service | sudo tee /etc/systemd/system/zotbins-dashboard.service
sudo systemctl daemon-reload
sudo systemctl enable --now zotbins-local-api zotbins-dashboard
```
After changing the dashboard code, rebuild it (`npm run build`) and `sudo systemctl restart zotbins-dashboard`.

## Future Implementations
Here is the bare minimum requirements for deployment:
- IR-Sensor Readings (Completed)
- Camera Streaming (Completed)
- Ultrasonic Reading (Not Completed)
- Weight Reading (Not Completed)
- AWS Integration (Not Completed)
