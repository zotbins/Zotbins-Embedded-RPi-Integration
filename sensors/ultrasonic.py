import pigpio
import time


def ultrasonic_process(input_queue, output_queue, trig_pin, echo_pin, samples):
    print("[Ultrasonic] Started")
    
    pi = _initialize_pigpio(trig_pin, echo_pin)
    if not pi:
        return
    
    try:
        while True:
            data = input_queue.get()            
            distance = _measure_distance(pi, trig_pin, echo_pin)
            data['distance'] = distance
            output_queue.put(data)
            print(f"[Ultrasonic] Distance: {distance:.2f} cm")
            
    except KeyboardInterrupt:
        print("[Ultrasonic] Shutting down")
    finally:
        pi.stop()


def _initialize_pigpio(trig_pin, echo_pin):
    pi = pigpio.pi()
    
    if not pi.connected:
        print("[Ultrasonic] Failed to connect to pigpio daemon")
    
    pi.set_mode(trig_pin, pigpio.OUTPUT)
    pi.set_mode(echo_pin, pigpio.INPUT)
    
    return pi


def _measure_distance(pi, trig_pin, echo_pin, timeout=0.1):
    pi.gpio_trigger(trig_pin, 10, 1)  
    pulse_start = _wait_for_pin_state(pi, echo_pin, 1, timeout)
    pulse_end = _wait_for_pin_state(pi, echo_pin, 0, timeout)
    pulse_duration = pulse_end - pulse_start
    return (pulse_duration * 34300) / 2


def _wait_for_pin_state(pi, pin, target_state, timeout):
    start = time.time()
    while pi.read(pin) != target_state:
        if time.time() - start > timeout:
            break
    return time.time()