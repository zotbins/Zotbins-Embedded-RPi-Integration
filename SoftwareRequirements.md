# Software Requirements

## Date: Feb 15, 2026

### Author: Kaveh Zare

### Requirements for a proper OS:

1. Initialize All modules in a non-blocking way

    a. camera test
    b. ultrasonic init (arduino)
    c. photoresistor init (arduino)
    d. break beam init
    e. wifi connectivity (paired with watchdog)
        i. set up MQTT message broker
        ii. set up MQTT client (to receive inference)

2. Photoresistor and Break Beam should be in an infinite while loop

3. Wifi watch dog should be triggered at every 10sec interval if not connected

4. If Wifi is down, save data locally (designate a *backup dir*)

5. If Photoresistor and Break Beam are triggered, record 5-10 images via the
   camera and either:
   a. save locally, along with weight, measured 3 seconds after trash disposal
      and ultrasonic reading for depth
   b. send via MQTT message broker

### Externally

1. Set Up MQTT clients:
    a. Turing Pi
    b. AWS server to receive data from the Turing Pi about inference & other data
     and save into database layer
    c. Raspberry Pi to receive inference

2. Set Up MQTT message broker:
    a. RPi to receive inference


### MQTT Setup

1. device/sensor/telemetry: weight and depth levels
2. device/camera/raw: image data
3. inference/request: sent to Turing Pi and AWS
4. inference/result: received by Raspberry Pi to trigger future actions (sorting)

**Notes**

- The communication payload is a JSON published to the MQTT broker

- potential MQTT payload structure:


```JSON
{
  "timestamp" : "YYYY-MM-DD:HH:MM:SSS",
  "device_id" : 001,
  "sensors"   : {
      "weight_grams" : 2345,
      "depth_cm"     : 30.5,
                },
  "image_count" : 5,
  "storage_path": "/rpi/backup/directory"
}
```


