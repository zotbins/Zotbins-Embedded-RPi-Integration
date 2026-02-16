import time
import multiprocessing as mp
import RPi.GPIO as GPIO

def ir_sensor_process(output_queue, gpio_pin=17, debounce_time=3):
    print("[IR] Started")
    
    # Initialize GPIO
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    
    trigger_count = 0
    last_trigger_time = 0
    last_state = GPIO.input(gpio_pin)

    try:
        while True:
            current_state = GPIO.input(gpio_pin)
            
            # Determine if beam is triggered
            if _is_beam_broken(current_state, last_state):
                current_time = time.time()
                
                if _is_debounced(current_time, last_trigger_time, debounce_time):
                    trigger_count += 1
                    last_trigger_time = current_time
                    
                    output_queue.put({'trigger': trigger_count})
                    print("--------------------------------Started Cycle--------------------------------")
                    print(f"[IR] Trigger #{trigger_count}")
            
            last_state = current_state
            time.sleep(0.01)
            
    except KeyboardInterrupt:
        print("[IR] Shutting down")
    finally:
        GPIO.cleanup()


def _is_beam_broken(current_state, last_state):
    return current_state != last_state and current_state == 0


def _is_debounced(current_time, last_trigger_time, debounce_time):
    return current_time - last_trigger_time >= debounce_time