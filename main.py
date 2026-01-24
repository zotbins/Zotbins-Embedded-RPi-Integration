#!/usr/bin/env python3
"""
main.py - Main script to intialize and run sensor processing pipeline.
"""

import multiprocessing as mp
import time
import sys

# Sensor Script Imports
from sensors.ir_sensor import ir_sensor_process
from sensors.camera import camera_process
from sensors.ultrasonic import ultrasonic_process
from sensors.weight import weight_process

def main():

	# Queues between sensor processing
	ir_to_camera = mp.Queue(maxsize=5)
	camera_to_ultrasonic = mp.Queue(maxsize=5)
	ultrasonic_to_weight = mp.Queue(maxsize=5)
	final_results = mp.Queue(maxsize = 5) 

	# Pin Configurations (subject to change)
	config = {
		"ir_gpio_pin": 17, # IR sensor pin
		"camera_duration": 2.0, # How long the camera runs for
		"ultrasonic_trig_pin" : 23,  # Ultrasonic Trigger Pin
		"ultrasonic_echo_pin" : 24,  # Ultrasonic Echo Pin
		"ultrasonic_samples" : 5,  # Number of Samples from Ultrasonic
		"weight_dout_pin" : 5, # Weight Data Out Pin
		"weight_sck_pin" : 6, # Serial Clock Input Pin
		"weight_samples" :  10 # Weight Samples Taken
	}

	proccesses = []

	# IR Sensor Process
	print("Creating IR Sensor Process")
	p1 = mp.Process(
		target = ir_sensor_process,
		args=(ir_to_camera, config['ir_gpio_pin']),
		name="ir_sensor"		
	)
	proccesses.append(p1)	

	# Camera Process
	print("Creating Camera Process")
	p2 = mp.Process(
		target = camera_process,
		args=(ir_to_camera, camera_to_ultrasonic, config["camera_duration"]),
		name="camera"		
	)
	proccesses.append(p2)	

	# Ultrasonic Process
	print("Creating Ultrasonic Process")
	p3 = mp.Process(
		target = ultrasonic_process,
		args=(camera_to_ultrasonic, ultrasonic_to_weight,
		      config["ultrasonic_trig_pin"], config["ultrasonic_echo_pin"], config["ultrasonic_samples"]),
		name = "ultrasonic"
	)
	proccesses.append(p3)

	# Weight Process
	print("Creating Weight Process")
	p4 = mp.Process(
		target = weight_process,
		args=(ultrasonic_to_weight, final_results, 
		      config["weight_dout_pin"], config["weight_sck_pin"],
		      config["weight_samples"]),
		name="weight"
	)
	proccesses.append(p4)

	print("Start All Proccesses...")
	for p in proccesses:
		p.start()
		print(f"Started: {p.name}")
		time.sleep(0.2)
	
	print("All Proccesses Running!")

	while True:
		try:
			result = final_results.get(timeout=1.0)
			print("Final Result Calculated")
			print(result)
		except  mp.queues.Empty:
			continue

if __name__ == "__main__":
	main()

