# Zotbins Raspberry PI Integration

## Program Description
Implements the sensors individually and then makes each a process. The program will run the processes in the following order: 
IR-Sensor (Usage) -> Camera Stream -> Ultrasonic Reading -> Weight Reading -> Send Data -> Repeat

## How to Run
The code only works on the Raspberry Pi 4 and requires Linux to be used. Once you setup a RPi4 use the following instruction to run the code: 
```
git clone https://github.com/zotbins/Zotbins-Embedded-RPi-Integration.git
cd {project_directory}
```
Create and activate virtual environment:
```
python3 -m venv .venv
source .venv/bin/activate
```
Download the required python packages:
```
pip install -r requirements.txt
```
In order to use the camera/GPIOs the RaspberryPi needs to have permission:
```
sudo usermod -aG gpio $USER
sudo usermod -aG video $USER
```
Now make project executable and run:
```
chmod +x main.py
./main.py 
```

## Future Implementations
Here is the bare minimum requirements for deployment:
- IR-Sensor Readings (Completed)
- Camera Streaming (Completed) 
- Ultrasonic Reading (Not Completed)
- Weight Reading (Not Completed)
- AWS Integration (Not Completed) 