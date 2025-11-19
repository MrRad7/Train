#!/home/mrrad/trainsite/bin/python
# python functions related to controlling the wemo switches

from __future__ import print_function
import os
import sys
import time
import subprocess
import logging
import psutil
##from configparser import SafeConfigParser
from configparser import ConfigParser



#command is:  wemo.sh <IP addr> GETSTATE/ON/OFF
CMD = '/home/mrrad/trainsite/wemo.sh'


def remove_newline(text):
	text = text.replace("\r","")
	text = text.replace("\n","")
	return text


def get_wemo_state(ip, mac='FF:FF:FF:FF:FF:FF'):
    # state of 1 or 8 both mean 'ON'
	print("Wemo IP address: " + str(ip))
	result = subprocess.check_output([CMD, ip, 'GETSTATE'])
	result = result.decode('utf-8')
	#print(result)
	result = result.split('=')
	#print("Result: " + str(result))
	if(remove_newline(result[0]) == '8'): #this also means ON
                result = 'ON'
        #print("LEN Result: " + str(len(result)))
	elif(len(result) == 2):
                result = result[1] #just want what's right of the newline
                result = remove_newline(result)
                #print("Result: " + str(result))
	else:
                result = 'ERROR'

	if(result in ['ON','OFF']):
		return result
	else:
		return 'ERROR'


def change_wemo_state(ip, new_state='OFF', mac='FF:FF:FF:FF:FF:FF'):
	new_state = new_state.upper()
	#print("New_State: " + str(new_state))

	if((new_state == 'ON') or (new_state == 'OFF')):
                current_state = str(get_wemo_state(ip)).upper()
                time.sleep(2)
                #print("CurrentState: " + str(current_state))

                if(new_state == current_state):
                        return new_state
                else:
                        result = subprocess.check_output([CMD, ip, new_state])
                        result = result.decode('utf-8')
                        result = remove_newline(result)
                        #print("Result: " + str(result))
                        if(result == '0'):
                                return 'OFF'
                        elif (result == '1'):
                                return 'ON'
                        else:
                                return 'ERROR'
	else:
		print("State must be ON or OFF")
		return 'ERROR'			

##### MAIN SECTION #####################
if __name__ == "__main__":
    print("Running Wemo tests.", file=sys.stderr)
    
    config_file = '/home/mrrad/trainsite/train_server.config'
    
    #parse config file
    parser = ConfigParser()
    
    try:
        parser.read(config_file)
    except:
        print("Cannot open configuration file: (%s); exiting." % (config_file), file=sys.stderr)
        sys.exit()

    wemo_ip = parser.get('train_server', 'wemo_ip')
    wemo_mac = parser.get('train_server', 'wemo_mac')
    
    log_filename = parser.get('train_server', 'log_filename')

    log_level = parser.get('train_server', 'log_level')
    

    #print("LOGLEVEL=",log_level, file=sys.stderr)

    #translate string log level to a numeric log level
    numeric_level = getattr(logging, log_level.upper(), 10)

    #print("NUMERIC_LEVEL=",numeric_level, file=sys.stderr)
        
    #open log file
    try:
        #logging.basicConfig(filename=log_filename, level=logging.DEBUG)
        logging.basicConfig(filename=log_filename, level=numeric_level)
    except IOError as e:
        print(f"Could not open log file: {log_filename}  {e}", file=sys.stderr)
        print("Exiting.", file=sys.stderr)
        sys.exit()

    logging.info("Starting Wemo Test.")

    print("Status tests...")
    result = get_wemo_state(wemo_ip)
    print(f"Train wemo: {result}")

    

