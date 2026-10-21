# Zotbins Raspberry PI Integration

## Program Description
Runs on a Raspberry Pi 3 or 4 as two processes:

- **IR watcher** (own process): checks the beam level every 10 ms and sends a trigger when it changes. By default that's when it goes clear (the lid opens); set `ir_trigger_on` to `"broken"` in `config.py` for the opposite.
- **Pipeline** (main process), once per trigger:
  Camera (detect object passing in the top two-thirds of the view, keep the frame where it looks biggest) -> wait for the trash to settle -> Ultrasonic (fullness) and Weight -> save the event. Each reading has its own settle time in `config.py` (`ultrasonic_settle_time`, `weight_settle_time`), counted from when the object leaves the frame.
- **Uploader** (background thread): sends stored events to the API oldest first. If the network is down, they're retried every 10 s.

Every event is kept permanently, whether or not it's uploaded:
- `data/events.db` (SQLite): one row per event with its time (`ts`, with UTC offset), `fullness` (0-1), `distance_cm`, `weight_g`, the classifier's `bin` and `bin_confidence` (full output in `classification`), the picture's path, and `upload` (`pending` / `uploaded` / `rejected` by the API).
- `data/images/<date>/<id>.jpg`: the picture of the item. The id is the event's local time, e.g. `20261020T181923_562`.

Nothing is deleted, except that if free disk space drops below `min_free_disk_mb` the oldest *pictures* are removed (their events stay). To look at the data: `sqlite3 data/events.db "SELECT ts, fullness, bin FROM events ORDER BY ts DESC LIMIT 20"`, or copy `events.db` to a PC and open it with any SQLite viewer. Records from the old `data/spool/` and `data/history/` folders are moved in automatically the first time the pipeline starts.

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
Three services, all started automatically when the Pi boots:

| Service | What it runs |
|---|---|
| `zotbins` | The pipeline (`main.py` in the `.venv`), restarted automatically if it crashes |
| `zotbins-local-api` | The local API the dashboard reads from (see Local Dashboard) |
| `zotbins-dashboard` | The dashboard on port 9999 (see Local Dashboard) |

Install the pipeline service (run from this repo):
```
sed "s|@USER@|$USER|g; s|@DIR@|$PWD|g" deploy/zotbins.service | sudo tee /etc/systemd/system/zotbins.service
sudo systemctl daemon-reload
sudo systemctl enable --now zotbins
```

Everyday commands:
```
journalctl -u zotbins -f                     # live pipeline log (Ctrl+C stops watching, not the service)
sudo systemctl restart zotbins               # after a git pull or a config.py change
sudo systemctl stop zotbins                  # before running main.py or a sensor test by hand
sudo systemctl start zotbins                 # start it again afterwards
systemctl status zotbins zotbins-local-api zotbins-dashboard
```
The service owns the camera and GPIO pins while it runs, so stop it before running `python main.py`
or `python -m sensors.<name>` yourself.

## On-Device Classifier
Each captured item is classified on the Pi as **trash / recycle / compost** by the `wasterec` model
(EfficientNet-Lite2, int8 ONNX, in `models/`). The pipeline crops a square around the detected item
(the model was trained on single-item crops) and runs it during the settle wait, so it adds no delay.
The result is saved in each record under `classification` (bin, confidence, material, box) and shows up
on the local dashboard's composition chart and image labels.

- Needs `onnxruntime` (`pip install -r requirements.txt` in the `.venv`) and **64-bit** Raspberry Pi OS.
  If it's missing, the pipeline logs `Classifier unavailable` and carries on without it.
- Settings in `config.py`: `enable_classifier`, `classifier_threshold` (below it the item goes to
  `classifier_fallback`, "when in doubt, throw it out"), `classifier_crop_padding`.
- The material -> bin mapping is `bins` in `models/wasterec.json`; edit it for local recycling rules
  (no retraining needed). To update the model, replace both files in `models/` from the same export.

Tools (from the repo root, with the `.venv` active):
```
python -m wasterec.classify_bin --image data/images/<date>/<id>.jpg   # classify a saved photo
python -m wasterec.predict --image photo.jpg                  # per-material scores
python -m wasterec.evaluate_bins --data labeled_photos        # bin accuracy on <bin>/ or <material>/ folders
```
The `--camera` options of these tools open the camera themselves, so stop `main.py` first.

## Local Dashboard
The dashboard ([zotbins-data-visualizer](https://github.com/zotbins/zotbins-data-visualizer), a separate repo) can run on the Pi and show this bin's own records, without the cloud. `data/local_api.py` answers the dashboard's API requests (`/raw_data`, `/inferences`, `/waste-classes`) from `data/events.db`, and serves the images, so the dashboard shows the bin's whole history. The composition chart uses the on-device classifier's bin.

Fullness is reported as a fraction using `bin_empty_distance_cm` (sensor to the bottom of the empty bin, 40 in) and `bin_full_distance_cm` in `config.py`. The dashboard recalculates it from each stored `distance_cm`, so after changing these (and restarting `zotbins-local-api`) the whole history uses the new calibration.

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

### On the Pi's Own Screen
With a monitor on the Pi's HDMI 0 port (the micro-HDMI next to USB-C), the Pi logs in to the desktop by itself and shows the dashboard full-screen (`deploy/kiosk/zotbins-kiosk.sh`). The screen turns off after 5 minutes with the lid closed and no keyboard / mouse / touch input, and back on when the lid opens (`deploy/kiosk/screen_power.py`). It also moves the mouse pointer to the top-left corner at login and 10 s after the mouse was last used.

Install (run from this repo, then reboot):
```
install -Dm755 deploy/kiosk/zotbins-kiosk.sh ~/.local/bin/zotbins-kiosk
install -Dm755 deploy/kiosk/screen_power.py ~/.local/bin/zotbins-screen-power
mkdir -p ~/.config/autostart
for f in deploy/kiosk/*.desktop; do sed "s|@HOME@|$HOME|g" "$f" > ~/.config/autostart/$(basename "$f"); done
sudo raspi-config nonint do_boot_behaviour B4   # log in to the desktop automatically
sudo raspi-config nonint do_wayland W3          # labwc desktop; Chromium's kiosk window stays invisible under Wayfire 0.7
python3 deploy/kiosk/hide_cursor.py             # invisible mouse pointer (--undo to get it back)
sudo cp deploy/kiosk/99-zotbins-uinput.rules /etc/udev/rules.d/   # lets the screen watcher park the pointer top-left
```
To change the timeout, edit `--timeout` in `~/.config/autostart/zotbins-screen-power.desktop`. To stop showing the dashboard, delete the two `zotbins-*.desktop` files there.

## Future Implementations
Here is the bare minimum requirements for deployment:
- IR-Sensor Readings (Completed)
- Camera Streaming (Completed)
- Ultrasonic Reading (Not Completed)
- Weight Reading (Not Completed)
- AWS Integration (Not Completed)
