"""
Main Program - Starts all sensor processes
Publishes sensor data and photos separately to AWS
"""
import multiprocessing as mp
import time

from client.publish import publish

from sensors.ir_sensor import ir_sensor_process
from sensors.camera import camera_process
from sensors.ultrasonic import ultrasonic_process
from sensors.weight import weight_process


# Configuration
BIN_ID = "1"  # Your bin ID (string)
AUTO_PUBLISH = True  # Set to False to disable AWS publishing


def main():
    # Create queues
    ir_to_camera = mp.Queue(maxsize=10)
    camera_to_ultrasonic = mp.Queue(maxsize=10)
    ultrasonic_to_weight = mp.Queue(maxsize=5)
    final_results = mp.Queue(maxsize=100)
    
    # Sensor configuration
    config = {
        'ir_gpio_pin': 17,
        'camera_duration': 2.0,
        'ultrasonic_trig_pin': 23,
        'ultrasonic_echo_pin': 24,
        'ultrasonic_samples': 5,
        'weight_dout_pin': 5,
        'weight_sck_pin': 6,
        'weight_samples': 10
    }
    
    # Create processes
    processes = [
        mp.Process(
            target=ir_sensor_process, 
            args=(ir_to_camera, config['ir_gpio_pin']), 
            name="IR"
        ),
        mp.Process(
            target=camera_process, 
            args=(ir_to_camera, camera_to_ultrasonic, config['camera_duration']), 
            name="Camera"
        ),
        mp.Process(
            target=ultrasonic_process, 
            args=(camera_to_ultrasonic, ultrasonic_to_weight, 
                  config['ultrasonic_trig_pin'], config['ultrasonic_echo_pin'], 
                  config['ultrasonic_samples']), 
            name="Ultrasonic"
        ),
        mp.Process(
            target=weight_process, 
            args=(ultrasonic_to_weight, final_results, 
                  config['weight_dout_pin'], config['weight_sck_pin'], 
                  config['weight_samples']), 
            name="Weight"
        )
    ]
    
    # Start all processes
    print("\nStarting processes...")
    for p in processes:
        p.start()
        print(f"  ✓ {p.name}")
        time.sleep(0.1)
    
    print("\nAll processes running!\n")
    
    try:
        while True:
            try:
                result = final_results.get(timeout=1.0)
                
                # Publish to AWS
                if AUTO_PUBLISH:
                    send_result = publish(BIN_ID, result)
                
            except mp.queues.Empty:
                continue
                
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        for p in reversed(processes):
            p.terminate()
            p.join(timeout=2)


if __name__ == '__main__':
    main()