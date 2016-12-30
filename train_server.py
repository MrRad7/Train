#!/home/pi/trainsite/bin/python
##!/usr/bin/python
# Version 2.1

from __future__ import print_function
import os
import sys
import time
import random
import RPi.GPIO as GPIO
import requests
#apt-get install libxml2-dev libxslt-dev python-dev 
from lxml import html
import re
from threading import Thread
import threading
import multiprocessing
import logging
import gevent
from gevent.wsgi import WSGIServer
from gevent.queue import Queue
from flask import Flask, Response, render_template, jsonify
import calendar
import pytz
import datetime
import pyping
import json
import subprocess
import signal
#import Queue
# ouimeaux is for the WeMo controls
from ouimeaux.environment import Environment
from ouimeaux.signals import statechange, receiver
#pika is for rabbitMQ
import pika
import uuid
import psutil
from ConfigParser import SafeConfigParser

#requires fping


config_file = 'train_server.config'

# Set initial/default values
mycommand = ''

# mode 1 = just do the train circle
# mode 2 = just do the train straight shuttle
# mode 3 = alternate modes 1 and 2
mode = 1 #default value

relay_status = {'Relay-01': 'OFF', 'Relay-02': 'OFF', 'Relay-03': 'OFF', 'Relay-04': 'OFF'}
loop_count = 0
#time_count = 0
max_loop_count = 0
max_time_count = 0
total_loop_count = 0
loop_time = 0
loops_left = 0

loop_timer_thread = None
shuttle_timer_thread = None

last_state = 0
current_state = 0

current_wemo_state = 0

STOP = 0

#mag sensor timestamps used for speed and safety calculations
mag_sensor1_ts = 0
mag_sensor2_ts = 0
mag_sensor3_ts = 0
mag_sensor4_ts = 0
mag_sensor5_ts = 0

#codes for the relay server
RELAY1_OFF = "00"  #station lights OFF
RELAY1_ON = "01"   #station lights ON

RELAY2_OFF = "02"
RELAY2_ON = "03"

RELAY3_OFF = "04"
RELAY3_ON = "05"

RELAY4_OFF = "06"
RELAY4_ON = "07"  

RELAY5_OFF = "08" # Section 1 power OFF (station)
RELAY5_ON = "09"  # Section 1 power ON (station)

RELAY6_OFF = "10" # Section 2 power OFF (tram station)
RELAY6_ON = "11"  # Section 2 power ON (tram station)

RELAY7_OFF = "12" # Section 3 power ON (safety stop)
RELAY7_ON = "13"  # Section 3 power ON (safety stop)

RELAY8_OFF = "14"
RELAY8_ON = "15"

RELAY_ALL_OFF = "44"
RELAY_ALL_ON = "45"


# SSE "protocol" is described here: http://mzl.la/UPFyxY
class ServerSentEvent(object):

    def __init__(self, data):
        self.data = data
        self.event = None
        self.id = None
        self.desc_map = {
            self.data : "data",
            self.event : "event",
            self.id : "id"
        }

    def encode(self):
        if not self.data:
            return ""
        lines = ["%s: %s" % (v, k) 
                 for k, v in self.desc_map.iteritems() if k]
        
        return "%s\n\n" % "\n".join(lines)

app = Flask(__name__)
subscriptions = []

# Client code consumes like this.
@app.route("/old")
def index():
    debug_template = """
     <html>
       <head>
       </head>
       <body>
         <h1>Server sent events</h1>
         <div id="event"></div>
         <script type="text/javascript">

         var eventOutputContainer = document.getElementById("event");
         var evtSrc = new EventSource("/subscribe");

         evtSrc.onmessage = function(e) {
             console.log(e.data);
             eventOutputContainer.innerHTML = e.data;
         };

         </script>
       </body>
     </html>
    """
    return(debug_template)

@app.route('/')
def jq2():
        return render_template('jq2.html')

@app.route("/mode/<data>", methods=['POST'])
def update_mode(data):

    return "OK"


@app.route('/restart')
def restart():
        logging.info("Restarting Train-Server.")
        res = os.popen('systemctl restart train-server > /dev/null 2>&1').readline()
        return "OK"

#@app.route("/lights/<data>", methods=['POST'])
@app.route("/lights/<data>", methods=['POST'])
def lights(data):
        #outputFunction("IN LIGHTS")
        #print("LIGHTS", file=sys.stderr)
        #if request.method == 'POST':
        #    data = request.form
        #    outputFunction("DATA")
        if data == "ON":
            print("Lights ON", file=sys.stderr)
            logging.info("Lights ON")
            request_base = "http://" + relay_server + "/" + relay_server_port + "/" + RELAY1_ON
            # 00 to turn lights off
            page = requests.get(request_base)
            print(request_base, file=sys.stderr)
            #print page.text
        elif data == "OFF":
            print("Lights OFF", file=sys.stderr)
            logging.info("Lights OFF")
            request_base = "http://" + relay_server + "/" + relay_server_port + "/" + RELAY1_OFF
            #request_code = request_base + "01" #turn on relay 1
            page = requests.get(request_base)
            print(request_base, file=sys.stderr)
            #print page.text
        else:
            print("ERROR", file=sys.stderr)
                
        return "OK"

@app.route("/power/<data>", methods=['POST'])
def power(data):
    if data == "ON":
        #print("Power ON", file=sys.stderr)
        logging.info("Power ON")
        # read state and initialize relays
        switch.on()
    elif data == "OFF":
        print("Power OFF", file=sys.stderr)
        logging.info("Power OFF")
        #write state
        switch.off()
    else:
            print("ERROR", file=sys.stderr)
                
    return "OK"

#dash_button toggles the power when triggered from and Amazon Dash button
@app.route("/dash_button")
def dash_button():
    global current_wemo_state

    #get wemo status
    state = switch.get_state()
    #print("DashButton WeMo state is ", state, file=sys.stderr)
    logging.debug("DashButton WeMo state is %s", state)
    #print("DashButton Current state is ", current_wemo_state, file=sys.stderr)
    logging.debug("DashButton Current state is %s", current_wemo_state)
    
    if str(state) in ['1', '8']:
            #if state in [1, 8]: #1 and 8 both signify power is ON
            print("Turning power off...", file=sys.stderr)
            power("OFF")
    elif str(state) in ['0']:
            print("Turning power on...", file=sys.stderr)
            power("ON")
            
    
    return "OK"

@app.route("/startstop/<data>", methods=['POST'])
def startstop(data):
        if data == "START":
            #print("Starting...", file=sys.stderr)
            logging.info("Starting...")
        elif data == "STOP":
            #print("Stopping", file=sys.stderr)
            logging.info("Stopping")
        else:
            #print("ERROR", file=sys.stderr)
            logging.error("ERROR")
                
        return "OK"
    
@app.route("/debug")
def debug():
    return "Currently %d subscriptions" % len(subscriptions)

@app.route("/publish/<data>")
def publish(data):
    #Dummy data - pick up from request for real data
    ####data is a string
    def notify():
        human_time = str(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())))
        #mydata = str(data)
        #msg = str(time.time()) + " : "+ str(data) + '\n'
        #msg = str(human_time) + " : "+ str(data) + '\n'
        #msg = human_time + " : " + mydata + '\n'

        #data_type = type(data)
        #print("DataType=",data_type, file=sys.stderr)
        
        msg = {}
        #msg['timestamp'] = human_time
        #msg['data'] = data

        msg = data

        #data_type = type(msg)
        #print("MessgaeType=",data_type, file=sys.stderr)
        

        msg = msg.replace("'", '"') #replace single quotes with double quotes
        
        parsed_json_dict = json.loads(msg)  #convert json string to dictionary

        parsed_json_dict['timestamp'] = human_time  #add timestamp to dict

        #data_type = type(parsed_json_dict)
        #print("JSON1Type=",data_type, file=sys.stderr)

        #json1 = "{\"message\":[" + json.dumps(msg) + "]}"

        json1 = json.dumps(parsed_json_dict) #convert dict back to string to send
        
        print("JSON1Message=",json1, file=sys.stderr)
        #print("Message=",msg, file=sys.stderr)
        #msg = "{'timestamp': + "\'" + human_time"
        for sub in subscriptions[:]:
            #sub.put(msg)
            sub.put(json1)
    
    gevent.spawn(notify)
    
    return "OK"

@app.route("/subscribe")
def subscribe():
    def gen():
        q = Queue()
        subscriptions.append(q)
        try:
            while True:
                result = q.get()
                ev = ServerSentEvent(str(result))
                yield ev.encode()
        except GeneratorExit: # Or maybe use flask signals
            subscriptions.remove(q)

    return Response(gen(), mimetype="text/event-stream")


#mag_sensor1 is above Thomas opposite the station
def mag_sensor1_callback(channel):
	global mag_sensor1_ts
	
	#reduce false positives
	time.sleep(0.05)
	if GPIO.input(mag_sensor1) != GPIO.LOW:
                #print("False Positive on Sensor 1!", file=sys.stderr)
                logging.debug("False Positive on Sensor 1!")
		return

	epoch_time = int(time.time())
	#print("mag_sensor1 at %s." % (epoch_time), file=sys.stderr)         

	mag_sensor1_ts = epoch_time
	msg = "mag_sensor1 at " + str(epoch_time)
	#msg = "{'message': " + "\'" + msg + "\'" + "}"
	msg = "{'type': 'message', 'value': " + "\'" + msg + "\'" + "}"
	outputFunction(str(msg))

	if loops_left == 0:
            #print("Cutting power to 70% ", file=sys.stderr)
            logging.info("Cutting power to 70% ")
	
	

#mag_sensor2 is after the station	
def mag_sensor2_callback(channel):
        global mag_sensor2_ts
        
	#reduce false positives
	time.sleep(0.05)
	if GPIO.input(mag_sensor2) != GPIO.HIGH:
                #print("False Positive on Sensor 2!", file=sys.stderr)
                logging.debug("False Positive on Sensor 2!")
		return

	epoch_time = int(time.time())
	mag_sensor2_ts = epoch_time
	
	msg = "mag_sensor2 at " + str(epoch_time)
	msg = "{'type': 'message', 'value': " + "\'" + msg + "\'" + "}"
	outputFunction(str(msg))
	


#mag_sensor3 is at the end of the straight	
def mag_sensor3_callback(channel):
        global mag_sensor3_ts
        
	#reduce false positives
	time.sleep(0.05)
	if GPIO.input(mag_sensor3) != GPIO.LOW:
                #print("False Positive on Sensor 3!", file=sys.stderr)
                logging.debug("False Positive on Sensor 3!")
		return

	epoch_time = int(time.time())
	mag_sensor3_ts = epoch_time

	msg = "mag_sensor3 at " + str(epoch_time)
	msg = "{'type': 'message', 'value': " + "\'" + msg + "\'" + "}"
	outputFunction(str(msg))
	
    

#mag_sensor4 is halfway down the straight	
def mag_sensor4_callback(channel):
	global loop_time
	global mag_sensor4_ts
	
	#reduce false positives
	time.sleep(0.05)
	if GPIO.input(mag_sensor4) != GPIO.LOW:
                #print("False Positive on Sensor 4!", file=sys.stderr)
                logging.debug("False Positive on Sensor 4!")
		return

	epoch_time = int(time.time())
	mag_sensor4_ts = epoch_time
	

        msg = "mag_sensor4 at " + str(epoch_time)
	msg = "{'type': 'message', 'value': " + "\'" + msg + "\'" + "}"
	outputFunction(str(msg))
	
	#loop_time = epoch_time - loop_time

#mag_sensor5 is at the start of the straight	
def mag_sensor5_callback(channel):
        global loop_count
	global total_loop_count
	global loops_left
	global loop_time
	global mag_sensor5_ts
	
	#reduce false positives
	time.sleep(0.05)
	if GPIO.input(mag_sensor5) != GPIO.LOW:
		#print("False Positive on Sensor 5!", file=sys.stderr)
		logging.debug("False Positive on Sensor 1!")
		return

        #print("Sensor 5!!!!!!", file=sys.stderr)
        
	epoch_time = int(time.time())
	mag_sensor5_ts = epoch_time
	

	msg = "mag_sensor5 at " + str(epoch_time)
	msg = "{'type': 'message', 'value': " + "\'" + msg + "\'" + "}"
	outputFunction(str(msg))
	
	#loop_time = epoch_time - loop_time
	loop_count += 1
	total_loop_count += 1
	#loops_left = max_loop_count - loop_count
	loops_left = loops_left - 1
	loop_time = epoch_time - loop_time

        #update loop count
        current_time = int(time.time())

        msg = "\'%s\'" % (loops_left)
        msg = "{'type': 'loops_left', 'value': " + msg + "}"
        outputFunction(str(msg))
        
        #if current_time > max_time_count  or loop_count >= max_loop_count
        if (current_time > max_time_count) or (loops_left <= 0):
            #print("LOOP OVER...", file=sys.stderr)
            logging.info("LOOP OVER...")
            end_loop()

	
	

def outputFunction(data):
    # data needs to be a string!
    print(data, file=sys.stderr)
    request_base = "http://localhost:5000/publish/" + str(data)
    page = requests.get(request_base)
    
def returnRandom(max=10, min=1):
	out = random.SystemRandom().randint(min,max)
	print(out, file=sys.stderr)
	return out


def TEMP():
    speed = 0
    
    while True:
        print("Speed=%s " % (speed), file=sys.stderr)
        logging.debug("Speed=%s ", speed)
        if STOP == 1:
                return

        if mode == 1:
            timediff = mag_sensor2_ts - mag_sensor1_ts
            speed = timediff / 20
            msg = "\'%s\'" % (speed)

        
        msg = "{'type': 'speed', 'value': " + msg + "}"
        outputFunction(str(msg))
        #MS1=1457210058  MS2=1457210085 Speed=0 Mode=1

        time.sleep(60)
    
def getTrainSpeed_thread():
    while True:
            if STOP == 1:
                    return

            timediff = 0.0
            speed = 0.0
            if mode == 1:
                timediff = int(mag_sensor2_ts) - int(mag_sensor1_ts)
                if (timediff > 0):
                    speed = float(20) / float(timediff)
                    speed = round(speed, 3)
                else:
                    speed = 0.0
                msg = "\'%s\'" % (speed)

            else:
                #timediff = int(mag_sensor4_ts - mag_sensor5_ts)
                #speed = timediff / 20
                speed = 0.0
                msg = "\'%s\'" % (speed)

            
            msg = "{'type': 'speed', 'value': " + msg + "}"
            outputFunction(str(msg))    

            #print("MS1=%s  MS2=%s TD=%s Speed=%s Mode=%s" % (mag_sensor1_ts, mag_sensor2_ts, timediff, speed, mode), file=sys.stderr)
            logging.debug("MS1=%s  MS2=%s TD=%s Speed=%s Mode=%s", mag_sensor1_ts, mag_sensor2_ts, timediff, speed, mode)

            time.sleep(30)
    
def getCPUtemperature_thread():
	while True:
		if STOP == 1:
			return
		res = os.popen('vcgencmd measure_temp').readline()
		temp = res.replace("temp=","").replace("'C\n","")
		temp = float(temp)
	
		fahrenheit = 9.0/5.0 * temp + 32
		#print "Temp=%s %s " % (temp, fahrenheit)
		msg = "\'%s %s\'" % (temp, fahrenheit)
		print("Temp=%s %s " % (temp, fahrenheit), file=sys.stderr)
		logging.debug("Temp=%s %s ", temp, fahrenheit)

                
                msg = "{'type': 'temp', 'value': " + msg + "}"
                outputFunction(str(msg))
	
		if temp > 55:
			#print("R-Pi too hot, exiting", file=sys.stderr)
			logging.error("R-Pi too hot, exiting")
			sys.exit()
		time.sleep(60)
	
def join_all_threads():
	main_thread = threading.currentThread()
	for t in threading.enumerate():
		if t is main_thread:
			continue
		thread_name = t.getName()
		#print("Thread name = %s" % thread_name, file=sys.stderr)
		if thread_name.startswith('Dummy'):
                        continue
		#print("Joining %s" % (t.getName()), file=sys.stderr)
		logging.debug("Joining %s", t.getName())
		t.join(1.0)

def strip_non_printable(text):
	return ''.join(i for i in text if ord(i)<128)	


# all_relays_off turns off all of the relays
# used when first starting and when stopping the server
def all_relays_off():
    logging.info("Turning All Relays OFF")
    request_base = "http://" + relay_server + "/" + relay_server_port + "/" + RELAY_ALL_OFF
    page = requests.get(request_base)
    print(request_base, file=sys.stderr)
    retval = 0
    

# section_control turns track sections on or off
# section: what section to turn on/off
# state: 0 = off, 1 = on
def section_control(section, state):
        retval = -1
        if section == 1: #Relay5 - wall near bathroom
            if state == "OFF":
                #turn off
                #print("Section1 OFF", file=sys.stderr)
                logging.info("Section1 OFF")
                request_base = "http://" + relay_server + "/" + relay_server_port + "/" + RELAY5_OFF
                page = requests.get(request_base)
                print(request_base, file=sys.stderr)
                retval = 0
            if state == "ON":
                #turn on
                #print("Section1 ON", file=sys.stderr)
                logging.info("Section1 ON")
                request_base = "http://" + relay_server + "/" + relay_server_port + "/" + RELAY5_ON
                page = requests.get(request_base)
                print(request_base, file=sys.stderr)
                retval = 0

        if section == 2: #Relay6 - near closet
            if state == "OFF":
                #turn off
                #print("Section2 OFF", file=sys.stderr)
                logging.info("Section2 OFF")
                request_base = "http://" + relay_server + "/" + relay_server_port + "/" + RELAY6_OFF
                page = requests.get(request_base)
                print(request_base, file=sys.stderr)
                retval = 0
            if state == "ON":
                #turn on
                #print("Section2 ON", file=sys.stderr)
                logging.info("Section2 ON")
                request_base = "http://" + relay_server + "/" + relay_server_port + "/" + RELAY6_ON
                page = requests.get(request_base)
                print(request_base, file=sys.stderr)
                retval = 0

        if section == 3: #Relay7 - near HVAC
            if state == "OFF":
                #turn off 
                #print("Section3 OFF", file=sys.stderr)
                logging.info("Section3 OFF")
                request_base = "http://" + relay_server + "/" + relay_server_port + "/" + RELAY7_OFF
                page = requests.get(request_base)
                print(request_base, file=sys.stderr)
                retval = 0
            if state == "ON":
                #turn on
                #print("Section3 ON", file=sys.stderr)
                logging.info("Section3 ON")
                request_base = "http://" + relay_server + "/" + relay_server_port + "/" + RELAY7_ON
                page = requests.get(request_base)
                print(request_base, file=sys.stderr)
                retval = 0
                
        return retval
    

def update_relay_status():
	#global relay_server
	#global relay_server_port
	global relay_status
	good_relay_list = []

	request_base = "http://" + relay_server + "/" + relay_server_port +"/42"
	#request_code = request_base + "01" #turn on relay 1
	page = requests.get(request_base)
	#print page.text
	tree = html.fromstring(page.text)
	relays1 = tree.xpath('//p//text()')

	request_base = "http://" + relay_server + "/" + relay_server_port +"/43"
	page = requests.get(request_base)
	#print page.text
	tree = html.fromstring(page.text)
	relays2 = tree.xpath('//p//text()')

	relays = relays1 + relays2
	#print "RELAYS: ", relays


	for item in relays:
		item = item.strip() #strip leading and trailing whitespace
		item = item.replace("&nbsp","")
		item = strip_non_printable(item)
		item = re.sub(r"\s", "", item)
		item = item.replace(':', "")
		item = item.replace(' ', "")
		if item == "": #blank line
			#print "BLANK"
			continue
		if item == "Relay-ALLON":
			continue
		if item == "ALL-ON":
			continue
		if item == "Relay-ALLOFF":
			continue
		if item == "ALL-OFF":
			continue
		if re.match('^ON/OFF', item):
			continue
		if re.match('^ChangeIP', item):
			continue
		if item == "Enter":
			continue
		if item == "NextPage":
			continue
		
		good_relay_list.append(item)
		

	i = 0
	while i < len(good_relay_list):
		#print good_relay_list[i]
		#print "Relay=%s State=%s" % (good_relay_list[i], good_relay_list[i+1])
		relay_status[good_relay_list[i]] = good_relay_list[i+1]
		i = i + 2

	for key in sorted(relay_status):
		print(key, relay_status[key], file=sys.stderr)

	return relay_status


# health_check monitors the status of necessary functions and resets as necessary.
# This is run as a thread in a constant loop
def health_check():
    while True:
        check_wemo()
        check_relay_server()

        time.sleep(60)
        
    return 0


# loop_timer is a failsafe/backup mode for counting down train loops.
# the primary method of counting are the magenetic sensors.
# If loop_timer activates, it will set the loop_count to zero and call end_loop()
def loop_timer(loops):
    print("\nStarting loop_timer.... %s" % str(loops))
    time.sleep(loops)

    # if the loop_counter is working then this isn't needed.
    if (loops_left <= 0):
        print("\nEnding loop_timer...")
        end_loop()
    
    return 0


def operating_mode():
    # mode is a global variable
    global max_loop_count
    global max_time_count
    global loops_left
    global loop_timer_thread
    global shuttle_timer_thread
    
    #mode = 1
    print("OPERATING MODE = %s" % str(mode))
    
    if mode == 1:
            #print("Just doing the loop.", file=sys.stderr)
            logging.info("Just doing the loop.")
            max_loop_count = returnRandom()
            loops_left = max_loop_count
            msg = "\'%s\'" % (max_loop_count)
            msg = "{'type': 'loops_left', 'value': " + msg + "}"
            outputFunction(str(msg))
            time_count = int(time.time())
            max_time_count = (max_loop_count * 60) + time_count #1 minute per loop in seconds
            
            #print("Looping %s times." % (max_loop_count), file=sys.stderr)
            logging.info("Looping %s times.", max_loop_count)
            state_file.write(str(mode))

            gertbot_wrapper("stop")
            
            # Turn off straight shuttle tracks (Relay6)
            section_control(2,"OFF")
            # Turn on loop tracks (Relay5 and Relay7)
            section_control(1,"ON")
            section_control(3,"ON")
            
            time.sleep(2)
        
            gertbot_wrapper("start_b")

            #start a loop_timer_thread
            loop_timer_thread = threading.Thread(target=loop_timer, args=((max_loop_count * 60),))
            loop_timer_thread.start()
    elif mode == 2:
            #print("Just doing the straight shuttle", file=sys.stderr)
            logging.info("Just doing the straight shuttle")
            
            """
            # Turn off loop tracks (Relay5 and Relay7)
            section_control(1,"OFF")
            section_control(3,"OFF")

            section_control(2,"OFF") #temporary

            max_loop_count = returnRandom()
            loops_left = max_loop_count
            msg = "\'%s\'" % (max_loop_count)
            msg = "{'type': 'loops_left', 'value': " + msg + "}"
            outputFunction(str(msg))
            time_count = int(time.time())
            max_time_count = (max_loop_count * 60) + time_count #1 minute per loop in seconds
            
            #print("Looping %s times." % (max_loop_count), file=sys.stderr)
            logging.info("Looping %s times.", max_loop_count)
            state_file.write(str(mode))
            """
            
            # Turn on shuttle tracks (Relay6)
    elif mode == 3:
            #print("Alternating loop and straight shuttle modes", file=sys.stderr)
            logging.info("Alternating loop and straight shuttle modes")
            
    return 0


#end_loop is run when loops_left < 0
def end_loop():
    if mode == 1:
        #print("Restarting mode 1", file=sys.stderr)
        logging.debug("Restaring mode 1")

        #remove loop_timer_thread
        try:
            loop_timer_thread.join()
        except:
            logging.debug("JOIN on loop_timer_thread failed.")
            
        #stop section 1
        section_control(1,"OFF")

        #wait 60 seconds - this is like a station stop.
        time.sleep(60)

        #call operating_mode()  to restart
        operating_mode()

    elif mode == 2:
        #print("Restaring mode 2", file=sys.stderr)
        logging.debug("Restaring mode 2")
        #determine direction
        #if direction = A, wait until direction switches to B
        #stop sections 2 and 3
        #wait 60 seconds
        #call operating_mode() to restart

    elif mode == 3:
        #print("Restaring mode 3", file=sys.stderr)
        logging.debug("Restaring mode 3")
        #alernating between modes 1 and 2
        
    return 0


def update_function():
    global current_wemo_state

    #print("Getting relay status.", file=sys.stderr)
    logging.info("Getting relay status.")
    current_relay_status = update_relay_status()
    msg = str(current_relay_status)
    msg = "{'type': 'relay_status', 'value': [" + msg + "]}"
    outputFunction(str(msg))

    #get wemo status
    state = switch.get_state()
    #print("WeMo state is ", state, file=sys.stderr)
    #print("Current state is ", current_wemo_state, file=sys.stderr)
    logging.info("WeMo state is %s", state)
    logging.info("Current state is %s", current_wemo_state)
    #print("Looping..", file=sys.stderr)
    if state != current_wemo_state:  #power state changed
        #print("WeMo power state changed! ", file=sys.stderr)
        logging.info("WeMo power state changed!")
        if (str(state) == '8') and (str(current_wemo_state) == '1'):
            # don't do anything
            #break
            #print("JUNK...", file=sys.stderr)
            logging.debug("JUNK...")
        elif (str(state) == '1') and (str(current_wemo_state) == '8'):
            # don't do anything
            #break
            #print("JUNK1...", file=sys.stderr)
            logging.debug("JUNK1...")
        elif str(state) in ['1', '8']:
            #if state in [1, 8]: #1 and 8 both signify power is ON
            #print("Ramping up power...", file=sys.stderr)
            logging.info("Ramping up power...")
            #what mode
            operating_mode()
        elif str(state) == '0': #power is now off
                print("Turning off power...", file=sys.stderr)
                gertbot_wrapper("stop")
                #turn off relays
                section_control(1,"OFF")
                section_control(2,"OFF")
                section_control(3,"OFF")
                
        current_wemo_state = state
                
    msg = "{'type': 'power_status', 'value': \"" + str(current_wemo_state) + "\"}"    
    outputFunction(str(msg))

    #update loop count
    #current_time = int(time.time())
    #loops_left = max_loop_count - loop_count
    #if current_time > max_time_count  or loop_count >= max_loop_count
    #if (current_time > max_time_count) or (loops_left < 0):
    #    print("LOOP OVER...", file=sys.stderr)
    #    end_loop()
        
    msg = "\'%s\'" % (loops_left)
    msg = "{'type': 'loops_left', 'value': " + msg + "}"
    outputFunction(str(msg))

        
def start_status_update():
    while True:
        update_function()
        
        time.sleep(20)
    
    
def stop_circle_train():
	#print("Stopping circle train.", file=sys.stderr)
	logging.info("Stopping circle train.")
	#reset loop count
	#max_loop_count = returnRandom()
	

def start_webserver():
	#Start the flask web server
        app.debug = True
        server = WSGIServer(("", 5000), app)
        server.serve_forever()
        # Then visit http://localhost:5000 to subscribe 
        # and send messages by visiting http://localhost:5000/publish

   


def gertbot_wrapper(mycommand):
    #print("GertbotCommand = %s\n" % (mycommand))
    logging.debug("GertbotCommand = %s", (mycommand))
    command_json = json.dumps({"command" : str(mycommand)}, sort_keys=True)

    #make connection to rabbitmq
    try:
        gertbot_rpc = GertbotRpcClient()
    except:
        logging.error("Cannot make GertbotRpcClient() connection!")
        return -1
    

    try:
        response = gertbot_rpc.call(command_json)
    except:
        #print("Gertbot_rpc.call failed for (%s)\n" % (mycommand), file=sys.stderr)
        logging.error("Gertbot_rpc.call failed for (%s)", (mycommand))
        return -1
    
    #print("Response of %s = %s" % (mycommand, response), file=sys.stderr)
    logging.debug("Response of %s = %s", mycommand, response)

    #close connection to rabbitmq
    gertbot_rpc.close()
                      
    return 0



class GertbotRpcClient(object):
    def __init__(self):
        self.connection = pika.BlockingConnection(pika.ConnectionParameters(
                host='localhost'))

        self.channel = self.connection.channel()

        result = self.channel.queue_declare(exclusive=True)
        self.callback_queue = result.method.queue

        self.channel.basic_consume(self.on_response, no_ack=True,
                                   queue=self.callback_queue)

    def on_response(self, ch, method, props, body):
        if self.corr_id == props.correlation_id:
            self.response = str(body.decode("utf-8","strict"))

    def close(self):
        self.connection.close()

    def call(self, n):
        self.response = None
        self.corr_id = str(uuid.uuid4())
        try:
            self.channel.basic_publish(exchange='',
                                       routing_key='gertbot_queue',
                                       properties=pika.BasicProperties(
                                             reply_to = self.callback_queue,
                                             correlation_id = self.corr_id,
                                             ),
                                       body=str(n))
        except:
                logging.debug('Reconnecting to rabbitmq/gertbot queue.')
                
        while self.response is None:
            self.connection.process_data_events()
        return str(self.response)

def check_rabbitmq():
    # Make sure that RabbitMQ is running!
    if os.path.exists(rabbitmq_pid_file):
            try:
                f = open(rabbitmq_pid_file, 'r')    
            except:
                #print("Cannot open pid file for RabbitMQ (%s), exiting." % (rabbitmq_pid_file), file=sys.stderr)
                logging.error("Cannot open pid file for RabbitMQ (%s), exiting.", (rabbitmq_pid_file))
                sys.exit()
            else:
                rabbitmq_pid = f.read()
                f.close()
                #output("PID=%s" % (rabbitmq_pid))
                if not psutil.pid_exists(int(rabbitmq_pid)):
                    print("RabbitMQ-server doesn't seem to be running, exiting.", file=sys.stderr)
                    sys.exit()
    else:
        print("PID file does not exist (%s), exiting." % (rabbitmq_pid_file), file=sys.stderr)
        sys.exit()    

def rabbitmq_keepalive_thread():
    # keeps the connection to rabbitmq alive - disable timeout
    # just requests a status update every 5 minutes
    # this works for now but isn't the best solution
    while True:
	if STOP == 1:
	    return
        try:
            response = gertbot_wrapper("status")
        except:
            logging.error("Gerbot status update failed in keepalive!")

        time.sleep(300)
        
    return 0


def signal_term_handler(signal, frame):
    logging.error("GOT SIGTERM!!!")
    #print("SIGNAL Got %s" % str(signal), file=sys.stderr) 	
    cleanup()
    

def check_wemo():
    res = os.popen('fping -c 1  -g 192.168.1.0/24 > /dev/null 2>&1').readline()
    #print(res, file=sys.stderr)

    wemo_cmd = "arp -n |grep -i \"" + wemo_mac + "\" |awk \'{print $1}\'"
    wemo_ip = os.popen(wemo_cmd).readline()
    #print("Wemo IP address is ", wemo_ip, file=sys.stderr)
    logging.info("Wemo IP address is %s", wemo_ip)
    
    r = pyping.ping(wemo_ip)
    #print(r.ret_code, file=sys.stderr)
    if r.ret_code == 0:
        #print("Wemo is reachable.", file=sys.stderr)
        logging.info("Wemo is reachable.")
    else:
        print("Wemo is NOT reachable, exiting.", file=sys.stderr)
        logging.error("Wemo is NOT reachable, exiting.")
        #sys.exit()
        # to restart from command line
        #os.execv(sys.argv[0], sys.argv)
        #or to restart from systemctl
        restart()
        
    return 0


def check_relay_server():
    #print("Relay Server IP address is ", relay_server, file=sys.stderr)
    logging.info("Relay Server IP address is %s", relay_server)
    r = pyping.ping(relay_server)
    #print(r.ret_code, file=sys.stderr)
    if r.ret_code == 0:
        #print("Relay Server is reachable.", file=sys.stderr)
        logging.info("Relay Server is reachable.")
    else:
        print("Relay Server is NOT reachable, exiting.", file=sys.stderr)
        logging.error("Relay Server is NOT reachable, exiting.")
        #
        # Need a way to remotely reset the relay server
        #
        #sys.exit()
        # to restart from command line
        #os.execv(sys.argv[0], sys.argv)
        #or to restart from systemctl
        restart()
        
    return 0


def cleanup(): 	
    STOP = 1
    
    join_all_threads()

    #make sure that train is stopped
    gertbot_wrapper("stop")
    #turn off relays
    all_relays_off()
    
    print("Loop count=%s" % (loop_count), file=sys.stderr)

    GPIO.cleanup()
    
    sys.exit(0)

##### MAIN SECTION #####################
if __name__ == "__main__":
    print("Running train server.", file=sys.stderr)

    #parse config file
    parser = SafeConfigParser()
    
    try:
        parser.read(config_file)
    except:
        print("Cannot open configuration file: (%s); exiting." % (config_file), file=sys.stderr)
        sys.exit()
        
    wemo_ip = parser.get('train_server', 'wemo_ip')
    wemo_mac = parser.get('train_server', 'wemo_mac')
    relay_server = parser.get('train_server', 'relay_server')
    relay_server_port = parser.get('train_server', 'relay_server_port')
    log_filename = parser.get('train_server', 'log_filename')
    state_filename = parser.get('train_server', 'state_filename')
    rabbitmq_pid_file = parser.get('train_server', 'rabbitmq_pid_file')
    log_level = parser.get('train_server', 'log_level')
    

    #print("LOGLEVEL=",log_level, file=sys.stderr)

    #translate string log level to a numeric log level
    numeric_level = getattr(logging, log_level.upper(), 10)

    #print("NUMERIC_LEVEL=",numeric_level, file=sys.stderr)

    #open log file
    try:
        #logging.basicConfig(filename=log_filename, level=logging.DEBUG)
        logging.basicConfig(filename=log_filename, level=numeric_level)
    except IOError:
           print("Could not open log file:", log_filename, file=sys.stderr)
           print("Exiting.", file=sys.stderr)
           sys.exit()

    logging.info("Starting train_server.")

    #open state file and read      
    try:
            state_file = open(state_filename, "r")
            last_state = state_file.readline()
            state_file.close()
    except IOError:
            #print("Could not open state file for reading, Setting mode to 1:", state_filename, file=sys.stderr)
            logging.error("Could not open state file for reading. Setting mode to 1")
            last_state = 1
            
    #open state file for writing
    try:
            state_file = open(state_filename, "w", 0)
            current_state = mode
            logging.debug("Current_State: %s", current_state)
            state_file.write(str(current_state))
    except IOError:
            #print("Could not open state file for writing, Exiting:", state_filename, file=sys.stderr)
            logging.error("Could not open state file for writing. Exiting.")
            sys.exit()

    #check connectivity to wemo and relay_server
    #print("Checking connectivity to wemo and relay_server", file=sys.stderr)
    logging.info("Checking connectivity to wemo and relay_server")

    check_wemo()

    check_relay_server()
    
    

    
    GPIO.setmode(GPIO.BCM)

    # SENSOR SETUP
    mag_sensor1 = 12 #GPIO pin 12
    GPIO.setup(mag_sensor1, GPIO.IN, pull_up_down=GPIO.PUD_UP)  #active input with pullup
    #print GPIO.input(mag_sensor1)
    #bouncetime set to 5 seconds
    GPIO.add_event_detect(mag_sensor1, GPIO.RISING, callback=mag_sensor1_callback, bouncetime=5000)

    mag_sensor2 = 16 #GPIO pin 16
    GPIO.setup(mag_sensor2, GPIO.IN, pull_up_down=GPIO.PUD_UP)  #active input with pullup
    #print GPIO.input(mag_sensor2)
    #bouncetime set to 5 seconds
    GPIO.add_event_detect(mag_sensor2, GPIO.RISING, callback=mag_sensor2_callback, bouncetime=5000)

    mag_sensor3 = 20 #GPIO pin 20
    GPIO.setup(mag_sensor3, GPIO.IN, pull_up_down=GPIO.PUD_UP)  #active input with pullup
    #print GPIO.input(mag_sensor3)
    #bouncetime set to 5 seconds
    GPIO.add_event_detect(mag_sensor3, GPIO.RISING, callback=mag_sensor3_callback, bouncetime=5000)

    mag_sensor4 = 21 #GPIO pin 21
    GPIO.setup(mag_sensor4, GPIO.IN, pull_up_down=GPIO.PUD_UP)  #active input with pullup
    #print GPIO.input(mag_sensor4)
    #bouncetime set to 5 seconds
    GPIO.add_event_detect(mag_sensor4, GPIO.RISING, callback=mag_sensor4_callback, bouncetime=5000)

    mag_sensor5 = 26 #GPIO pin 26
    GPIO.setup(mag_sensor5, GPIO.IN, pull_up_down=GPIO.PUD_UP)  #active input with pullup
    #print GPIO.input(mag_sensor5)
    #bouncetime set to 5 seconds
    GPIO.add_event_detect(mag_sensor5, GPIO.RISING, callback=mag_sensor5_callback, bouncetime=5000)


    #initialize track sections by turning relays off
    all_relays_off()
    
    update_relay_status()
  
    # Need to start the webserver in it's own thread
    webserver_thread = Thread(target = start_webserver)
    webserver_thread.setDaemon(True)
    webserver_thread.start()
    
    # WeMo access
    # put some error checking around this
    env = Environment()
    env.start()
    env.discover(3) #used to discover WeMo devices on the network
    switch = env.get_switch('Train')
    #switch = env.get_switch('WeMo Insight Lamp')
    state = switch.get_state()
    #print("WeMo state is ", state, file=sys.stderr)
    logging.info("WeMo state is %s", state)
    current_wemo_state = state

    CPUTemp_thread = Thread(target = getCPUtemperature_thread)
    CPUTemp_thread.setDaemon(True)
    CPUTemp_thread.start()

    TrainSpeed_thread = Thread(target = getTrainSpeed_thread)
    TrainSpeed_thread.setDaemon(True)
    TrainSpeed_thread.start()

    # Start thread for status updates (send status every minute)
    update_status_thread = Thread(target = start_status_update)
    update_status_thread.setDaemon(True)
    update_status_thread.start()

    # Start thread to check health
    health_check_thread = Thread(target = health_check)
    health_check_thread.setDaemon(True)
    health_check_thread.start()
    
    # Reset to known state!
    # Need to save to a file
    # This part is only run when the program first starts!
    current_wemo_state = 0 #set initial wemo state to off

    #verify that rabbitmq is running before we go further
    check_rabbitmq()

    """   
    gertbot_rpc = GertbotRpcClient()
    #print(" [x] Requesting GertBot(status)")
    logging.info("[x] Requesting GertBot(status)")
    #command = start_a start_b stop status config version read_error emergency_stop
    command_json = json.dumps({"command" : 'status'}, sort_keys=True)
    """

    """
    #print("CommandJSON= %s" % (command_json), file=sys.stderr)
    logging.info("CommandJSON= %s", (command_json))
    response = gertbot_rpc.call(command_json)
    print(" [.] Got %s" % (response), file=sys.stderr)
    logging.info("[.] Got %s", (response))
    """

    """
    rabbitmq_thread = Thread(target = rabbitmq_keepalive_thread)
    rabbitmq_thread.setDaemon(True)
    rabbitmq_thread.start()
    """

    # Handle signal interrupts
    signal.signal(signal.SIGTERM, signal_term_handler)
    signal.signal(signal.SIGABRT, signal_term_handler)
    signal.signal(signal.SIGHUP, signal_term_handler)
    
    
    
    while True:
            try:
                    time.sleep(0.5)
                    
            except KeyboardInterrupt:
                    #catches CTRL-C
                    cleanup()
           
