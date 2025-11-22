#!/home/mrrad/trainsite/bin/python

# Version 4.0
# November 19, 2025

# Pololu motorcontroller to run the train.  Made things more generic.
# Pololu High-Power Simple Motor Controller G2 18v15
# https://www.pololu.com/product/1363
#
# Removed most of the global variables and installed a sqlite database
# Added a magnetic hall sensor to improve tracking accuracy.
#
#apt-get install libxml2-dev libxslt-dev python-dev

from __future__ import print_function
import os
import sys
import time
import random
import RPi.GPIO as GPIO
import requests
from lxml import html
import re
import threading
import multiprocessing
import logging
import gevent
from gevent.pywsgi import WSGIServer
from gevent.queue import Queue
from flask import Flask, Response, render_template, jsonify, request
import calendar
import pytz
import datetime
import ping3
import json
import subprocess
import signal
import pika  #pika is for rabbitMQ
import uuid
import psutil
from functools import partial

from configparser import ConfigParser
from wemo_functions import *

from trainsite_database import TrainDatabaseClass


stop_event = threading.Event() #used to stop threads



# Constants
LOOP = 1
TROLLEY = 2
RANDOM = 3
ON = 1
OFF = 0


app = Flask(__name__)
subscriptions = []


# SSE "protocol" is described here: http://mzl.la/UPFyxY
class ServerSentEvent(object):
    """ Used to send messages to the web site.  The messages are pushed automatically 
    to all subscribers.
    """
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
                 for k, v in self.desc_map.items() if k]
        
        return "%s\n\n" % "\n".join(lines)




def valid_json(json_string):
    """ Simple function to test for a valid json string.
    True if good, False if bad
    """
    try:
        json.loads(json_string)
    except:
        return False
    
    return True


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


@app.route("/modechange/<data>", methods=['POST'])
def modechange(data):
    validModes = ['0','1','2','3']
    logging.info("MODE: " + str(data))
    print("MODE: " + str(data))

    if data in validModes:
        logging.debug("Valid mode")
        #current_mode = TrainData.train_state_dict["mode"]
        current_mode = TrainDatabase.get_item("mode")
        logging.debug("Current mode: " + str(current_mode))
        # if data is the same as current_mode, just return
        if str(data) == str(current_mode):
            logging.debug("MODE is the same")
            return "OK"
        else:
            logging.debug("Changing the mode!")
            #operating_mode(data)  #needs to be added!!!!
            #update_state_object(TrainData, mode=data)
            result = TrainDatabase.update_record("mode", int(data)) #want it as an integer
            print(f"Result from mode update:  {result}")
           
            
        
    return "OK"


@app.route('/restart')
def restart():
        logging.info("Restarting Train-Server.")
        res = os.popen('systemctl restart train-server > /dev/null 2>&1').readline()
        return "OK"
    


@app.route("/lights/<data>", methods=['POST'])
def lights(data):
        if data == "ON":
            print("Lights ON", file=sys.stderr)
            logging.info("Lights ON")
            #lights_function("ON")
            relaycontroller_wrapper('1', 'ON')
            result = TrainDatabase.update_record("lights", 1)
            print(f"Result from lights update:  {result}")
        elif data == "OFF":
            print("Lights OFF", file=sys.stderr)
            logging.info("Lights OFF")
            #lights_function("OFF")
            relaycontroller_wrapper('1', 'OFF')
            #update_state_object(TrainData, lights=0)
            result = TrainDatabase.update_record("lights", 0) 
            print(f"Result from lights update:  {result}")
        else:
            print("ERROR", file=sys.stderr)
            logging.error("ERROR")
            return "ERROR"
        
        #print("Back in lights!")
                
        return "OK"


@app.route("/power/<data>", methods=['POST'])
def power(data):
    # read state and initialize relays
    state = get_wemo_state(wemo_ip)
    print(f"Wemo State = {state}")
    logging.debug("Wemo result: " + str(state))
    
    if data == "ON":
        #print("Power ON", file=sys.stderr)
        logging.info("Power ON")
        
        if state != "ON": #not currently on
            result = change_wemo_state(wemo_ip, 'ON')
            result = TrainDatabase.update_record("power", 1)
        else:
            pass #do nothing, it's already on        
    elif data == "OFF":
        print("Power OFF", file=sys.stderr)
        logging.info("Power OFF")     
         
        if state != "OFF": #not currently off
            #motorcontroller_wrapper("stop")
            motorcontroller_wrapper("slow_stop")
            result = change_wemo_state(wemo_ip, 'OFF')
            result = TrainDatabase.update_record("power", 0)
        else:
            pass #do nothing, it's already off
    else:
            print("ERROR; incorrect power state given.", file=sys.stderr)
                
    return "OK"


'''
def power(data):
    if data == "ON":
        #print("Power ON", file=sys.stderr)
        logging.info("Power ON")
        # read state and initialize relays
        result = change_wemo_state(wemo_ip, 'ON')
        state = get_wemo_state(wemo_ip)
        logging.debug("Wemo result: " + str(state))
        if(state == 'ON'):
            #update_state_object(TrainData, power=1)
            result = TrainDatabase.update_record("power", 1)
    elif data == "OFF":
        print("Power OFF", file=sys.stderr)
        logging.info("Power OFF")      
        #motorcontroller_wrapper("stop")
        result = change_wemo_state(wemo_ip, 'OFF')
        state = get_wemo_state(wemo_ip)
        logging.debug("Wemo result: " + str(state))
        if(state == 'OFF'):
            #update_state_object(TrainData, power=0)
            result = TrainDatabase.update_record("power", 0)
    else:
            print("ERROR", file=sys.stderr)
                
    return "OK"
'''



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
    

@app.route("/magnet", methods=['POST'])  #expect json values
def magnet():
    request_data = request.get_json()
    logging.info("MAGNET DETECTED " + str(type(request_data)))
    keys = request_data.keys()
    for i in keys:
        logging.info(str(i))
        logging.info(str(request_data[i]))
   
    
    print("MAGNET DETECTED")
        
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

        data_type = type(msg)
        #print("MessageType=",data_type, file=sys.stderr)
        #print("MESSAGE=",str(msg))

        msg = msg.replace("'", '"') #replace single quotes with double quotes
        
        #need error checking here!
        if (msg == 0) or (msg == '0'):
            print("JSON is Zero!")
            return "OK"
        elif (valid_json(msg)):
            #print("Valid JSON: " + str(msg))
            parsed_json_dict = json.loads(msg)  #convert json string to dictionary
            #print("ParsedJSONDict=", str(parsed_json_dict))
            
            parsed_json_dict['timestamp'] = human_time  #add timestamp to dict
            
            json1 = json.dumps(parsed_json_dict) #convert dict back to string to send
            
            #print("JSON1Message=",json1)
            #print("\n")
            
            #print("Message=",msg, file=sys.stderr)
            #msg = "{'timestamp': + "\'" + human_time"
        else:
            print("BAD JSON: " + str(msg))
            #json1 = '{"BAD JSON":' + str(msg) + '}'
            return "OK"
            
        
        
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





def check_wemo():
    """ Verifies that the Wemo smart outlet is reachable on the network.
    Requires a known MAC address for the Wemo smart outlet.
    """
    
    '''
    res = os.popen('fping -c 1  -g 192.168.1.0/24 > /dev/null 2>&1').readline()
    print(res, file=sys.stderr)

    wemo_cmd = "arp -n |grep -i \"" + wemo_mac + "\" |awk \'{print $1}\'"
    wemo_ip = os.popen(wemo_cmd).readline()
    print("Wemo IP address is ", wemo_ip, file=sys.stderr)
    logging.info("Wemo IP address is %s", wemo_ip)
    '''
  
    try:
        result = ping3.ping(wemo_ip)
    except BaseException as e:
        print("Wemo is NOT reachable, exiting.", file=sys.stderr)
        logging.error("Wemo is NOT reachable, exiting.")
        #restart()
        
    print("Wemo is reachable.", file=sys.stderr)
    logging.info("Wemo is reachable.")
        
    return 0
    
    



def start_webserver():
    """ Starts the flask webserver and runs forever. """
    #Start the flask web server
    #app.debug = True
    app.debug = False
    app.threaded = True
    app.use_reloader = False
    server = WSGIServer(("", 5000), app)
    server.serve_forever()
    # Then visit http://localhost:5000 to subscribe 
    # and send messages by visiting http://localhost:5000/publish
    


def join_all_threads():
    """ Ensures that all running threads terminate before the program terminates. """
    main_thread = threading.current_thread()
    for t in threading.enumerate():
        if t is main_thread:
            continue
        thread_name = t.name
        print("Thread name = %s" % thread_name, file=sys.stderr)
        if thread_name.startswith('Dummy'):
            continue
        print("Joining %s" % (t.name), file=sys.stderr)
        logging.debug("Joining %s", t.name)
        t.join(1.0)
        return 0


def strip_non_printable(text):
    """ Removes all non printable characters from a text string. """
    return ''.join(i for i in text if ord(i)<128)	



def motorcontroller_wrapper(mycommand):
    #print("MotorController Command = %s\n" % (mycommand))
    logging.debug("MotorController command = %s", (mycommand))
    command_json = json.dumps({"command" : str(mycommand)}, sort_keys=True)

    #make connection to rabbitmq
    try:
        motorcontroller_rpc = MotorControllerRpcClient()
    except:
        logging.error("Cannot make MotorControllerRpcClient() connection!")
        print("Cannot make MotorControllerRpcClient() connection!")
        return -1
    

    try:
        response = motorcontroller_rpc.call(command_json)
    except:
        print("MotorController_rpc.call failed for (%s)\n" % (mycommand), file=sys.stderr)
        logging.error("MotorController_rpc.call failed for (%s)", (mycommand))
        return -1
    
    #print("Response of %s = %s" % (mycommand, response), file=sys.stderr)
    logging.debug("Response of %s = %s", mycommand, response)
    msg = "{'type': 'motorcontroller_wrapper', 'value': " + str(response) + "}"
    
    #outputFunction(str(msg))  #returning the string instead of outputting

    #close connection to rabbitmq
    motorcontroller_rpc.close()
                      
    return str(msg)
    
    
class MotorControllerRpcClient(object):
    def __init__(self):
        self.connection = pika.BlockingConnection(pika.ConnectionParameters(
                host='localhost'))

        self.channel = self.connection.channel()

        result = self.channel.queue_declare(queue='', exclusive=True)
        #result = self.channel.queue_declare(queue='motorcontroller_queue',durable=True, exclusive=False, auto_delete=False)
        
        self.callback_queue = result.method.queue

        #self.channel.basic_consume(self.on_response, no_ack=True,
        #                           queue=self.callback_queue)

        self.channel.basic_consume(self.callback_queue, self.on_response, auto_ack=True)

    def on_response(self, ch, method, props, body):
        if self.corr_id == props.correlation_id:
            self.response = str(body.decode("utf-8","strict"))

    def close(self):
        self.connection.close()
        
    def call(self, n):
        self.response = None
        self.corr_id = str(uuid.uuid4())
        self.channel.basic_publish(exchange='',
                                   routing_key='motorcontroller_queue',
                                   properties=pika.BasicProperties(
                                         reply_to = self.callback_queue,
                                         correlation_id = self.corr_id,
                                         ),
                                   body=str(n))
        while self.response is None:
            self.connection.process_data_events()
        return str(self.response)
    


def all_relays_off():
	relaycontroller_wrapper("all_relays_off")
	return 0
	
'''
def lights_function(value="OFF"):
	if value == "ON":
		#print("Turning on lights.")
		relaycontroller_wrapper('1', 'ON')
	else:
		#print("Turning off lights.")
		relaycontroller_wrapper('1', 'OFF')
		
	return 0
'''


def publish_current_relay_status():
    current_relay_status = relaycontroller_wrapper("status")
    outputFunction(str(current_relay_status))
    return 0



def relaycontroller_wrapper(mycommand, value=None):
    #print("\nRelayController Command = " + str(mycommand) + " Value = " + str(value))
    logging.debug("RelayController command = %s  value= %s ", (mycommand), (value))
    command_json = json.dumps({"command" : str(mycommand), "value" : str(value)  }, sort_keys=True)
    
    
    #make connection to rabbitmq
    try:
        relaycontroller_rpc = RelayControllerRpcClient()
    except:
        logging.error("Cannot make RelayControllerRpcClient() connection!")
        #raise Exception("Cannot make RelayControllerRpcClient() connection!")
        #return -1
        cleanup("Cannot make RelayControllerRpcClient() connection!")
    

    try:
        #print("Command_JSON: " + str(command_json))
        response = relaycontroller_rpc.call(command_json)
    except:
        print("RelayController_rpc.call failed for (%s)\n" % (mycommand), file=sys.stderr)
        logging.error("RelayController_rpc.call failed for (%s)", (mycommand))
        #raise("RelayController_rpc.call failed ")
        #return -1
        cleanup("RelayController_rpc.call failed ")
    
    #print("Response of %s = %s" % (mycommand, response), file=sys.stderr)
    #print("Response of " + str(mycommand) + " = " + str(response), file=sys.stderr)
    logging.debug("Response of %s = %s", mycommand, response)
    
    if mycommand == "status":
        #print("RELAY STATUS")
        msg = "{'type': 'relay_status', 'value': " + str(response) + "}"
        #outputFunction(str(msg))
    elif mycommand == "all_relays_off":
        #print("All RELAYS OFF")
        msg = "{'type': 'all_relays_off', 'value': " + str(response) + "}"
        outputFunction(str(msg)) 
    else:
        #print("OTHER")
                
        command_response = {
            "type" : "other",
            "command": str(mycommand),
            "value" : json.loads(response) #take a json string and make it a dict
        }
        
        msg = json.dumps(command_response).replace('\\','')
        outputFunction(str(msg))
        
    #close connection to rabbitmq
    relaycontroller_rpc.close()
     
    return msg



class RelayControllerRpcClient(object):
    def __init__(self):
        self.lock = threading.Lock()
        self.connection = pika.BlockingConnection(pika.ConnectionParameters(
                host='localhost'))

        self.channel = self.connection.channel()

        #result = self.channel.queue_declare(queue='relaycontroller_queue',durable=False, exclusive=False, auto_delete=False)
        result = self.channel.queue_declare(queue='', exclusive=True)
        self.callback_queue = result.method.queue

	#self.channel.basic_consume(self.on_response, 
 	#                           queue=self.callback_queue)
                                  
        self.channel.basic_consume(self.callback_queue, self.on_response, auto_ack=True)
        
        self.response = None
        self.corr_id = None

    def on_response(self, ch, method, props, body):
        if self.corr_id == props.correlation_id:
            self.response = str(body.decode("utf-8","strict"))

    def close(self):
        self.channel.close()
        self.connection.close()
        
    def call(self, n):
        logging.debug("Waiting for a lock...")
        self.lock.acquire()
        
        self.response = None
        self.corr_id = str(uuid.uuid4())
        self.channel.basic_publish('',
                                   'relaycontroller_queue',
                                   properties=pika.BasicProperties(
                                         reply_to = self.callback_queue,
                                         correlation_id = self.corr_id,
                                         ),
                                   body=str(n))
        while self.response is None:
            self.connection.process_data_events()
        
        logging.debug("Releasing the lock...")    
        self.lock.release()
        return str(self.response)
        
        
    

def outputFunction(data):
    # data needs to be a string!
    data = str(data.replace("'", '"')) #replace single quotes with double quotes
    #print(data, file=sys.stderr)
    #print("OutputFunction: " + str(data))
    request_base = "http://localhost:5000/publish/" + str(data)
    
    print("Request_base: " + str(request_base))
    
    try:
    	page = requests.get(request_base, timeout=10)
    except:
    	logging.error("Cannot get request.")
    	print("Cannot get request." + str(request_base))
    	#raise("Cannot get request.")

    #print("Page: " +str(page))
    
    return 0


    

def cleanup(message=None): 	
    #STOP = 1  #don't think this is needed
    
    print("Cleaning up.")
    
    #make sure that train is stopped
    motorcontroller_wrapper("stop")

    #turn off train power
    power("OFF")
    result = change_wemo_state(wemo_ip, 'OFF')
    
    
    #turn off relays
    all_relays_off()
    time.sleep(1)
       
    #print("Loop count=%s" % (loop_count), file=sys.stderr)

    GPIO.cleanup()

    
    stop_event.set()
    #pause ?
    
    join_all_threads()
    
    print("Exiting Train-Server.")    
    raise SystemExit(message)
    #sys.exit("Exiting")
    
    

def check_rabbit_mq():
    #check if rabbitmq-server is running
    try:
        #stat = os.system("systemctl status rabbitmq-server")
        stat = subprocess.call(["systemctl", "is-active", "--quiet", "rabbitmq-server"])
    except ValueError as e:
        msg = "{'type': 'ERROR', 'value': " + str(e) + "}"
        outputFunction(str(msg))
        print("Error getting status of rabbitmq-server: %s" % str(e))

    if stat == 0: #this is good
        e = "'rabbitmq-server is running'"
        msg = "{'type': 'rabbitmq_status', 'value': " + str(e) + "}"
        outputFunction(str(msg))
    else:
        #rabbitmq-server is NOT running
        e = "'rabbitmq-server is NOT running!'"
        msg = "{'type': 'ERROR', 'value': " + str(e) + "}"
        outputFunction(str(msg))
        print("rabbitmq-server is NOT running!")
        e = "'rabbitmq-server is NOT running'"
        msg = "{'type': 'rabbitmq_status', 'value': " + str(e) + "}"
        outputFunction(str(msg))
        #attempt restart
        #result = subprocess.call(["systemctl", "restart", "rabbitmq-server"])
        
    return 0
    
    
    
def check_motorcontroller():
    #check if MotorController_app is running
    #motorcontroller_status updates the GUI
    try:
        #stat = os.system("systemctl status MotorController_app")
        #stat = subprocess.check_output("systemctl status MotorController_app", shell=True)
        stat = subprocess.call(["systemctl", "is-active", "--quiet", "MotorController_app"])
    except ValueError as e:
        msg = "{'type': 'ERROR', 'value': " + str(e) + "}"
        outputFunction(str(msg))
        print("Error getting status of MotorController_app: %s" % str(e)) 

    if stat == 0: #this is good
        #check motorcontroller status
        #motorcontroller_wrapper("status")
        e = "'MotorController_app is running'"
        msg = "{'type': 'motorcontroller_status', 'value': " + str(e) + "}"
        outputFunction(str(msg))
    else:
        #MotorController_app is NOT running
        e = "'MotorController_app is NOT running!'"
        msg = "{'type': 'ERROR', 'value': " + str(e) + "}"
        outputFunction(str(msg))
        print("MotorController_app is NOT running!")
        e = "'MotorController_app is NOT running'"
        msg = "{'type': 'motorcontroller_status', 'value': " + str(e) + "}"
        outputFunction(str(msg))
        #attempt restart?
        #result = subprocess.call(["systemctl", "restart", "MotorController_app"])
        
    return 0
    
       
   
def check_relaycontroller():
    #check if RelayController_app is running
    #relaycontroller_status updates the GUI
    #print("CHECKING RELAYCONTROLLER_STATUS !!!")
    try:
        #stat = os.system("systemctl status RelayController_app")
        stat = subprocess.call(["systemctl", "is-active", "--quiet", "RelayController_app"])
    except ValueError as e:
        msg = "{'type': 'ERROR', 'value': " + str(e) + "}"
        outputFunction(str(msg))
        print("Error getting status of RelayController_app: %s" % str(e)) 

    if stat == 0: #this is good
        #check relaycontroller status
        # need a timeout on this!
        #relaycontroller_wrapper("status")
        e = "'RelayController_app is running'"
        msg = "{'type': 'relaycontroller_status', 'value': " + str(e) + "}"
        outputFunction(str(msg))
    else:
        #RelayController_app is NOT running
        e = "'RelayController_app is NOT running!'"
        msg = "{'type': 'ERROR', 'value': " + str(e) + "}"
        outputFunction(str(msg))
        print("RelayController_app is NOT running!")
        e = "'RelayController_app is NOT running'"
        msg = "{'type': 'relaycontroller_status', 'value': " + str(e) + "}"
        outputFunction(str(msg))
        #attempt restart?
        #result = subprocess.call(["systemctl", "restart", "RelayController_app"])
    return 0


def getCPUtemperature():
        #print("in getCPUtemperature function.")
        
        res = os.popen('vcgencmd measure_temp').readline()
        temp = res.replace("temp=","").replace("'C\n","")
        temp = float(temp)
    
        fahrenheit = 9.0/5.0 * temp + 32
        fahrenheit = round(fahrenheit,2)
        
        #print "Temp=%s %s " % (temp, fahrenheit)
        msg = "\'%s %s\'" % (temp, fahrenheit)
        #print("Temp=%s %s " % (temp, fahrenheit), file=sys.stderr)
        logging.debug("Temp=%s %s ", temp, fahrenheit)
      
        msg = "{'type': 'temp', 'value': " + msg + "}"
        outputFunction(str(msg))
    
        if temp > 85:
            print("R-Pi too hot, exiting", file=sys.stderr)
            logging.error("R-Pi too hot, exiting")
            sys.exit()
             
 
 

 
 
    
# _check monitors the status of necessary functions and resets as necessary.
# This is run as a thread in a constant loop
def health_check():
	#outputFunction("\nIn Health_Check()\n")
	logging.debug("In Health Check")
	print("\nhealth_check\n")
	
	 
	try:
		check_wemo()
	except:
		cleanup("Cannot check_wemo." )
	
		
	try:
		#print("Checking rabbit_mq.")
		check_rabbit_mq()
	except:
		cleanup("Cannot check_rabbit_mq.")
	
			
	try:
		#print("Checking motorcontroller.")
		check_motorcontroller()
	except:
		cleanup("Cannot check_motorcontroller.")
	
		
	try:
		#print("Checking relaycontroller.")
		check_relaycontroller()
	except:
		cleanup("Cannot check relaycontroller.")
	
		
	try:
		getCPUtemperature() #there is a flaw in this function
	except:
		cleanup("Cannot getCPUtemperature.")
    

	#time.sleep(30)
        
	return 0
	  

	  
def health_check_thread(event):
    while not event.is_set():
        health_check()
        time.sleep(30)
    print("health_check_thread is stopping gracefully.")
    return 0
    
    

# update_function is run periodically to get the state of things.
# update_function also detects when the WeMo was powered on, such as by Alexa
def update_function():
    
    print("Getting relay status.", file=sys.stderr)
    logging.info("Getting relay status.")

    publish_current_relay_status()
    
    # get_wemo_state returns 'ON', 'OFF' or 'ERROR'
    state = get_wemo_state(wemo_ip)
    
    print("Wemo state is: ", state, file=sys.stderr) 
    logging.info("Wemo state is: %s", state)
    
    #current_mode = TrainDatabase.get_item("mode")
    
    current_wemo_state = TrainDatabase.get_item("current_wemo_state")
    if str(state) != str(current_wemo_state):  #power state changed
        #print("WeMo power state changed! ", file=sys.stderr)
        logging.info("Wemo power state changed!")
        if str(state) in ['1', 'ON']:  #changing to ON
            #print("Ramping up power...", file=sys.stderr)
            logging.info("Ramping up power...")
            #what mode?
            #operating_mode()  #start in whatever state it left off in
            result = TrainDatabase.update_record("power", 1)
        elif str(state) in ['0','OFF']: #changing to OFF
                print("Turning off power...", file=sys.stderr)
                motorcontroller_wrapper("stop")
                #turn off relays
                section_control(1,"OFF")
                section_control(2,"OFF")
                section_control(3,"OFF")
                #update_state_object(TrainData, power=0)
                result = TrainDatabase.update_record("power", 0)
                
        #Update current_wemo_state
        result = TrainDatabase.update_record("current_wemo_state", state)
                
    msg = "{'type': 'power_status', 'value': \"" + str(TrainDatabase.get_item("current_wemo_state")) + "\"}"    
    outputFunction(str(msg))

    current_mode = TrainDatabase.get_item("mode")
    msg = "{'type': 'mode', 'value': \"" + str(current_mode) + "\"}"    
    outputFunction(str(msg))
    
    #update loop count
    #current_time = int(time.time())
    #TrainData.loops_left = max_loop_count - loop_count
    #if current_time > max_time_count  or loop_count >= max_loop_count
    #if (current_time > max_time_count) or (TrainData.loops_left < 0):
    #    print("LOOP OVER...", file=sys.stderr)
    #    end_loop()
        
    msg = "\'%s\'" % (TrainDatabase.get_item("loops_left"))
    msg = "{'type': 'loops_left', 'value': " + msg + "}"
    outputFunction(str(msg))


    motorcontroller_info = motorcontroller_wrapper("info")  #gets output from the wrapper
    #substitute "motorcontroller_wrapper" with "motorcontroller_info"
    motorcontroller_info = str(motorcontroller_info).replace("motorcontroller_wrapper", "motorcontroller_info")
    #print("MOTORCONTROLLER_INFO: ", str(motorcontroller_info))
    outputFunction(str(motorcontroller_info))
    
    return 0



def signal_term_handler(signal, frame):
    logging.error("GOT SIGTERM!!!")
    print("SIGNAL Got %s" % str(signal), file=sys.stderr) 	
    cleanup()



def returnRandom(min=1, max=10):
	out = random.SystemRandom().randint(min,max)
	#print(out, file=sys.stderr)
	return out



# section_control turns track sections on or off
# section: what section to turn on/off
# state: 0 = off, 1 = on
def section_control(section, state):
        retval = -1 #initial/default value
        
        if section == 1: #Relay5 - wall near bathroom Station1
            if state == "OFF":
                #turn off
                #retval = section_1("OFF")
                retval = relaycontroller_wrapper('5', 'OFF')
                #update_state_object(TrainData, section1=0)
                result = TrainDatabase.update_record("section1", 0)
            if state == "ON":
                retval = relaycontroller_wrapper('5', 'ON')
                #update_state_object(TrainData, section1=1)
                result = TrainDatabase.update_record("section1", 1)
                

        if section == 2: #Relay6 - near closet Tram station
            if state == "OFF":
                #turn off
                retval = relaycontroller_wrapper('6', 'OFF')
                #update_state_object(TrainData, section2=0)
                result = TrainDatabase.update_record("section2", 0)
            if state == "ON":
                #turn on
                retval = relaycontroller_wrapper('6', 'ON')
                #update_state_object(TrainData, section2=1)
                result = TrainDatabase.update_record("section2", 1)

        if section == 3: #Relay7 - near HVAC safety_stop
            if state == "OFF":
                #turn off 
                retval = relaycontroller_wrapper('7', 'OFF')
                #update_state_object(TrainData, section3=0)
                result = TrainDatabase.update_record("section3", 0)
            if state == "ON":
                #turn on
                retval = relaycontroller_wrapper('7', 'ON')
                #update_state_object(TrainData, section3=1)
                result = TrainDatabase.update_record("section3", 1)
                
        return retval



def train_slow_stop():
    ''' Slows the train to 50% power and then stops
    '''
    motorcontroller_wrapper("slow_stop")
    return 0
    


def new_loop_count():
    # Get new randomized loop count
    TrainDatabase.max_loop_count = returnRandom(3, 5) #min,max
    TrainDatabase.loops_left = TrainDatabase.max_loop_count
    msg = "\'%s\'" % (TrainDatabase.max_loop_count)
    msg = "{'type': 'loops_left', 'value': " + msg + "}"
    outputFunction(str(msg))
    time_count = int(time.time())
    TrainDatabase.max_time_count = (TrainDatabase.max_loop_count * 60) + time_count #1 minute per loop in seconds
    
    #print("Looping %s times." % (TrainData.max_loop_count), file=sys.stderr)
    logging.info("Looping %s times.", TrainDatabase.max_loop_count)

    #update_state_object(TrainData, loops_left = TrainData.max_loop_count)
    result = TrainDatabase.update_record("loops_left", TrainDatabase.max_loop_count)
    
    return 0



def start_new_loop():
    ''' 
     Starts a new loop
     gets new_loop_count, turns on the track sections,
     starts the motor_controller and updates the database
    '''
    print("NEW loop.", file=sys.stderr)
    logging.info("NEW loop.")

    new_loop_count()
    
    
    motorcontroller_wrapper("stop") #just to be safe
    #time.sleep(2)
    
    # Turn off straight shuttle tracks (Relay6)
    section_control(2,"OFF") #trolley
    # Turn on loop tracks (Relay5 and Relay7)
    section_control(1,"ON") #station
    section_control(3,"ON") #HVAC/safety
    time.sleep(2)

    print("Calling motorcontroller_wrapper start_b")
    motorcontroller_wrapper("start_b")
    result = TrainDatabase.update_record("direction", "B")
    
    previous_mode = LOOP
    result = TrainDatabase.update_record("previous_mode", LOOP)

    #start a loop_timer_thread
    #loop_timer_thread = threading.Thread(target=loop_timer, args=((max_loop_count * 60),))
    #loop_timer_thread.start()
    
    return True
    


def loop_thread(event): 
    logging.debug("Starting loop thread.")
    #print("Starting loop thread.")

    while not event.is_set():  #if event is set, everything stops
        logging.debug("In loop thread.")
        #print("In loop thread.")

        current_mode = TrainDatabase.get_item("mode")
        logging.debug("CURRENT MODE: " + str(current_mode))

        previous_mode = TrainDatabase.get_item("previous_mode")
        logging.debug("Previous mode: " + str(previous_mode))
        #print("Previous mode: " + str(previous_mode))

        #IF POWER ISN'T ON DON'T DO ANYTHING
        #can't ensure correct state without power
        power_status = TrainDatabase.get_item("power")
        if int(power_status) == 1:
            if (int(current_mode) == LOOP): #enter loop mode
                #check previous condition
                if int(previous_mode) == TROLLEY: #switching from mode 2 to mode 1
                    logging.debug("Parking at the trolley station.")
                    print("Parking at the trolley station.")
                    #park_trolley()


                if int(previous_mode) == LOOP: #already doing loop mode
                    logging.debug("Already in loop mode.")
                    print("Already in loop mode.")   
                    pass
                else: #start a new loop
                    start_new_loop()
                    
                    
        else:
            print("No power, returning from loop_thread.")
            logging.debug("No power, returning from loop_thread.")
            if (int(power_status) == 0) and (int(current_mode) == LOOP) and (previous_mode == LOOP):
                previous_mode = 0 #this will cause a new loop when power comes back
                result = TrainDatabase.update_record("previous_mode", OFF)
            
        time.sleep(5)
        
    print("loop_thread is stopping gracefully.")
    return 0


'''
def loop_thread(event): 
    #previous_mode = TrainDatabase.get_item("previous_mode")
    
    #current_mode = TrainDatabase.get_item("mode")
    #previous_mode = current_mode   #same thing when starting, no change
    #counter = 0

    logging.debug("Starting loop thread.")
    #print("Starting loop thread.")

    while not event.is_set():  #if event is set, everything stops
        logging.debug("In loop thread.")
        #print("In loop thread.")

        current_mode = TrainDatabase.get_item("mode")
        logging.debug("CURRENT MODE: " + str(current_mode))

        previous_mode = TrainDatabase.get_item("previous_mode")
        logging.debug("Previous mode: " + str(previous_mode))
        #print("Previous mode: " + str(previous_mode))

        #IF POWER ISN'T ON DON'T DO ANYTHING
        #can't ensure correct state without power
        power_status = TrainDatabase.get_item("power")
        if int(power_status) == 1:
            if (int(current_mode) == LOOP): #enter loop mode
                #check previous condition
                if int(previous_mode) == TROLLEY: #switching from mode 2 to mode 1
                    logging.debug("Parking at the trolley station.")
                    #print("Parking at the trolley station.")
                    #park_trolley()


                if int(previous_mode) == LOOP: #already doing loop mode
                    logging.debug("Already in loop mode.")
                    print("Already in loop mode.")   
                else: #start a new loop
                    print("NEW loop.", file=sys.stderr)
                    logging.info("NEW loop.")

                    new_loop_count()
                    
                    
                    motorcontroller_wrapper("stop") #just to be safe
                    #time.sleep(2)
                    
                    # Turn off straight shuttle tracks (Relay6)
                    section_control(2,"OFF") #trolley
                    # Turn on loop tracks (Relay5 and Relay7)
                    section_control(1,"ON") #station
                    section_control(3,"ON") #HVAC/safety
                    time.sleep(2)

                    print("Calling motorcontroller_wrapper start_b")
                    motorcontroller_wrapper("start_b")
                    #update_state_object(TrainData, direction="B")
                    result = TrainDatabase.update_record("direction", "B")
                    
                    previous_mode = LOOP

                    #start a loop_timer_thread
                    #loop_timer_thread = threading.Thread(target=loop_timer, args=((max_loop_count * 60),))
                    #loop_timer_thread.start()
        else:
            print("No power, returning from loop_thread.")
            if (int(power_status) == 0) and (int(current_mode) == LOOP) and (previous_mode == 1):
                previous_mode = 0 #this will cause a new loop when power comes back
            
        time.sleep(5)
        
    print("loop_thread is stopping gracefully.")
    return 0
'''   
    

def park_loop():
    #global max_loop_count
    #global max_time_count
    #global loops_left
    #global loop_timer_thread
    #global shuttle_timer_thread

    logging.debug("Parking the loop train.")
    print("Parking the loop train.")

    #check for power?
    power_status = TrainDatabase.get_item("power")
    if int(power_status) == 1:
        # go in B direction
        section_control(1,"OFF") #station stays off during shuttle/trolley
        section_control(3,"OFF") #HVAC/safety
        section_control(2,"ON") #trolley
        time.sleep(2)
        print("PARK LOOP")
        motorcontroller_wrapper("stop")
        time.sleep(2)
        motorcontroller_wrapper("start_b")
        time.sleep(60) # 1 minutes sleep
    else:
        logging.debug("Power is not on, returning.")
        print("Power is not on, returning.")
        return 0
        
    return 0
    


#hall_sensor1 is at the start of the straight	
#channel is the pin number
def hall_sensor1_callback(channel):
	#print("Hall_Sensor1!!!!!!", file=sys.stderr)
	#logging.info("Hall_Sensor1 !!!!!!")
	

	#reduce false positives.  there are many false positives.
	# wait sleep time and then see if still high
	
	cur_value = GPIO.input(hall_sensor1)
	#print("TYPE for cur_value: ", str(type(cur_value)))
	#logging.debug("Current value = %s" % str(cur_value))
	
	#time.sleep(0.05) #original time
	#time.sleep(0.01) #new time
	#time.sleep(0.08 / 1000) #time in milliseconds - orig
	#time.sleep(0.20 / 1000) 
	time.sleep(0.1) 
	if GPIO.input(hall_sensor1) != GPIO.HIGH: #not still high after time
		#print("False Positive on Hall_Sensor_1!", file=sys.stderr)
		logging.debug("False Positive on Hall_sensor1!")
		return
	
	logging.info("") #blank	
	logging.info("Good Hall_sensor1")
	logging.info("") #blank
	
	#add logic here to deal with extra "good" hits
	time.sleep(1) #wait 1 second in between valid hits
		
	epoch_time = int(time.time())
	result = TrainDatabase.update_record("mag_sensor5_ts", epoch_time)
	
	msg = "hall_sensor1 at " + str(epoch_time)
	msg = "{'type': 'message', 'value': " + "\'" + msg + "\'" + "}"
	outputFunction(str(msg))
	
	#loop_time = epoch_time - loop_time
	#TrainData.loop_count += 1
	result = TrainDatabase.update_record("loop_count", TrainDatabase.get_item("loop_count") + 1)
	
	#TrainData.total_loop_count += 1
	result = TrainDatabase.update_record("total_loop_count", TrainDatabase.get_item("total_loop_count") + 1)
	
	#loops_left = max_loop_count - loop_count
	#TrainData.loops_left = TrainData.loops_left - 1
	loops_left = TrainDatabase.get_item("loops_left") #get current loops_left
	loops_left -= 1  #decrement loops_left by 1
	print(f"LOOPS LEFT: {loops_left}")
	result = TrainDatabase.update_record("loops_left", loops_left) #update with new value
	
	result = TrainDatabase.update_record("loop_time", epoch_time - TrainDatabase.get_item("loop_time") )
	

    #update loop count
	current_time = int(time.time())

	msg = "\'%s\'" % (loops_left)
	msg = "{'type': 'loops_left', 'value': " + msg + "}"
	outputFunction(str(msg))

	
	#result = TrainDatabase.update_record("loops_left", loops_left) #should be 1 lower than before
	result = TrainDatabase.update_record("last_location", 5)
	
	if (TrainDatabase.get_item("loops_left") <= 0):
            #print("LOOP OVER...", file=sys.stderr)
            logging.info("LOOP OVER...")
            # SLOW DOWN TRAIN
            #end_loop(TrainData)  #disabled for now, needs debugging!
	
	return 0
	
	
	
    
##### MAIN SECTION #####################
if __name__ == "__main__":
    print("Running train server.", file=sys.stderr)
    
    #TrainData = SharedData()
    
    TrainDatabase = TrainDatabaseClass(False) #new database, suppress SQL echo
    
    #parse config file
    parser = ConfigParser()
    
    try:
        parser.read(TrainDatabase.get_item("config_file"))
    except:
        print("Cannot open configuration file: (%s); exiting." % (TrainDatabase.get_item("config_file")), file=sys.stderr)
        sys.exit()
        
    wemo_ip = parser.get('train_server', 'wemo_ip')
    TrainDatabase.update_record("wemo_ip", wemo_ip)
    wemo_mac = parser.get('train_server', 'wemo_mac')
    TrainDatabase.update_record("wemo_mac", wemo_mac)
    log_filename = parser.get('train_server', 'log_filename')
    TrainDatabase.update_record("log_filename", log_filename)
    state_filename = parser.get('train_server', 'state_filename')
    TrainDatabase.update_record("state_filename", state_filename)
    rabbitmq_pid_file = parser.get('train_server', 'rabbitmq_pid_file')
    TrainDatabase.update_record("rabbitmq_pid_file", rabbitmq_pid_file)
    log_level = parser.get('train_server', 'log_level')
    TrainDatabase.update_record("log_level", log_level)
    

    #print("LOGLEVEL=",log_level, file=sys.stderr)

    #translate string log level to a numeric log level
    numeric_level = getattr(logging, log_level.upper(), 10)
    #print(f"numeric_level type = {type(numeric_level)}")
    #print("NUMERIC_LEVEL=",numeric_level, file=sys.stderr)
    print(f"Logging to:{log_filename}")

    #open log file
    try:
        #logging.basicConfig(filename=log_filename, level=logging.DEBUG)
        #FORMAT='%(asctime)s - %(levelname)s - %(message)s', datefmt="%Y-%m-%d %H:%M:%S')
        logging.basicConfig(filename=log_filename, filemode="a", force=True, level=numeric_level, format='%(asctime)s - %(levelname)s - %(message)s')
        #logging.basicConfig(filename='/var/log/TrainServer/train_log.log', filemode="a", force=True, level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    except IOError:
           print("Could not open log file:", log_filename, file=sys.stderr)
           print("Exiting.", file=sys.stderr)
           sys.exit()

    logging.info("Starting train_server.")
    
    
    #check connectivity to wemo
    logging.info("Checking connectivity to wemo.")
    check_wemo()
    
    
    # Need to start the webserver in it's own thread
    # start the webserver first!
    webserver_thread = threading.Thread(target=start_webserver, name="WebserverThread", daemon=True)
    webserver_thread.start()
    
    
    GPIO.setmode(GPIO.BCM)
    
    hall_sensor1 = 26 #GPIO pin 26
    GPIO.setup(hall_sensor1, GPIO.IN, pull_up_down=GPIO.PUD_UP)  
    #GPIO.add_event_detect(hall_sensor1, GPIO.RISING, callback=lambda x: hall_sensor1_callback()) #no bounce time
    GPIO.add_event_detect(hall_sensor1, GPIO.RISING, callback=hall_sensor1_callback) #no bounce time
    
    #initialize track sections by turning relays off
    all_relays_off()
    
    
    #relay_status = relaycontroller_wrapper("status")
    
    # WeMo access
    # put some error checking around this
    state = get_wemo_state(wemo_ip)
    logging.info("WeMo state is %s", state)
    current_wemo_state = state
    
    # Reset to known state!
    # Need to save to a file
    # This part is only run when the program first starts!
    #current_wemo_state = 0 #set initial wemo state to off
    
    #verify that rabbitmq is running before we go further
    check_rabbit_mq()
    
        
   
    
    # Start thread to check health
    health_check_thread = threading.Thread(target=health_check_thread, args=(stop_event,), name="HealthCheckThread", daemon=True)
    health_check_thread.start()

    # Reduce pika logging
    logging.getLogger("pika").setLevel(logging.WARNING)
    
    # Handle signal interrupts
    signal_handler_with_args = partial(signal_term_handler)
    signal.signal(signal.SIGTERM, signal_handler_with_args)
    signal.signal(signal.SIGABRT, signal_handler_with_args)
    signal.signal(signal.SIGHUP, signal_handler_with_args)
    #signal.signal(signal.SIGINT, signal_handler_with_args)
    
    
    # Start thread to check for trolley state
    #create_thread('trolley_thread', trolley_thread)

    # Start thread to check for loop state
    loop_thread = threading.Thread(target=loop_thread, args=(stop_event,), name="LoopThread")
    loop_thread.start()
    
    
    while True:
            try:
                    #getTrainSpeed_thread()
                    #health_check()  #currently run as a thread
                    update_function()
                    #time.sleep(0.5)
                    time.sleep(10)
            except KeyboardInterrupt:
                    #catches CTRL-C
                    print("Got CTRL-C, cleaning up!")
                    cleanup()
                    
            
    
    
