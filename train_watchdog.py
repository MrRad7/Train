#!/usr/bin/env python3
import os
import sys
import subprocess
import datetime

services = ['rabbitmq-server', 'MotorController_app', 'RelayController_app', 'train-server']

RelayController_app_client = '/home/pi/RelayController_app/rc_client.py'
MotorController_app_client = '/home/pi/MotorController_app/mc_client.py'


def outputFunction(data):
    # data needs to be a string!
    print(str(data), file=sys.stdout)
    return 0


def checkService(service):
    #outputFunction("Checking service: " + str(service))

    try:
        stat = subprocess.call(["systemctl", "is-active", "--quiet", service])
    except ValueError as e:
        msg = "{'type': 'ERROR', 'value': " + str(e) + "}"
        output(str(msg))
        print("Error getting status of %s: %s" % str(service),str(e)) 

    if stat == 0: #this is good
        #print("Service is running")
        return True
    else:
        #print("Service is NOT running")
        return False
        
    
    


def restartService(service):
    outputFunction("Restarting service: " + str(service))
    p = subprocess.Popen(["systemctl", "restart", service], stdout=subprocess.PIPE)

    (output,err) = p.communicate()
    output = output.decode('utf-8')

    #outputFunction(str(output))

    return 0


def checkRabbitmq():
    status = checkService("rabbitmq-server")
    print(status)
    if not status:
        print("Restarting rabbit")
    return 0


def extraRelayController_app():
    output = ''
    
    p = subprocess.Popen(["timeout", "20", RelayController_app_client, "health"], stdout=subprocess.PIPE)

    (output,err) = p.communicate()
    output = output.decode('utf-8')

    #outputFunction(str(output))

    if 'True' in output:
        #outputFunction("RelayController_app is repsonsive.")
        return True
    else:
        #outputFunction("RelayController_app is NOT responding.")
        return False
    

def extraMotorController_app():
    output = ''
    
    p = subprocess.Popen(["timeout", "20", MotorController_app_client, "status"], stdout=subprocess.PIPE)

    (output,err) = p.communicate()
    output = output.decode('utf-8')

    #outputFunction(str(output))

    if 'response' in output:
        #outputFunction("MotorController_app is repsonsive.")
        return True
    else:
        #outputFunction("MotorController_app is NOT responding.")
        return False
    


# main ##################
if __name__ == '__main__':
    current_time = datetime.datetime.now()

    outputFunction("Train Watchdog: " + str(current_time))
 
    # Check that the services are running.
    for service in services:
        outputFunction("Checking service: " + str(service))
        status = checkService(service)

        #print(status)
        if status is True:
            outputFunction("\tRunning")
        else:
            outputFunction("\tStopped")
            
        if not status: #service is NOT running
            restartService(service)

        #Extra checks
        if service == 'RelayController_app':
            #print("Extra for " + str(service))
            result = extraRelayController_app()
            if result == True:
                outputFunction("\tRelayController_app is repsonsive.")
            else:
                outputFunction("\tRelayController_app is NOT responding.")
                restartService(service)

        
        if service == 'MotorController_app':
            #print("Extra for " + str(service))
            result = extraMotorController_app()
            if result == True:
                outputFunction("\tMotorController_app is repsonsive.")
            else:
                outputFunction("\tMotorController_app is NOT responding.")
                restartService(service)
	


        outputFunction('\n')

