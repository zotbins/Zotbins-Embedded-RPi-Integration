# Zotbins Raspberry PI Integration

## Program Description
Runs on a Raspberry Pi 3 or 4 as two processes:

- **IR watcher** (own process): sleeps on a GPIO edge interrupt and sends a trigger when the beam breaks.
- **Pipeline** (main process), once per trigger:
  Camera (detect object passing, keep the middle frame) -> Ultrasonic (fullness) -> wait for the load cell to settle -> Weight -> save to spool
- **Uploader** (background thread): sends spooled records to the API oldest first. If the network is down, they stay on disk and are retried every 10 s.

Records are saved in `data/spool/` as `<timestamp>.jpg` + `<timestamp>.json`. Records the API refuses (4xx) are moved to `data/spool/rejected/`. The oldest are deleted past `max_records`.

All settings (pins, timings, API URL) are in `CONFIG` at the top of `main.py`.

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

## Run at Boot (systemd)
```
sed "s|@USER@|$USER|g; s|@DIR@|$PWD|g" deploy/zotbins.service | sudo tee /etc/systemd/system/zotbins.service
sudo systemctl daemon-reload
sudo systemctl enable --now zotbins
journalctl -u zotbins -f    # view logs
```

## Future Implementations
Here is the bare minimum requirements for deployment:
- IR-Sensor Readings (Completed)
- Camera Streaming (Completed)
- Ultrasonic Reading (Not Completed)
- Weight Reading (Not Completed)
- AWS Integration (Not Completed)
