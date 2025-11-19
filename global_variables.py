# global variables used in the trainsite project.
#from configparser import SafeConfigParser


class SharedData():
    config_file = '/home/mrrad/trainsite/train_server.config'

    # Set initial/default values
    mycommand = ''

    # mode 1 = just do the train circle
    # mode 2 = just do the train straight shuttle
    # mode 3 = alternate modes 1 and 2
    #mode = 1 #default value

    
    #these items used to be in train_state_dict
    power = 0  #boolean 0=off
    mode = 0  #0=none, 1=loop, 2=shuttle, 3=random
    direction ='B' #B is default direction for going around the loop
    loops_left = 0
    last_location = 1 #last sensor to see the train 1-5
    lights = 0   #boolean 0=off
    section1 = 0 #boolean 0=off
    section2 = 0 #boolean 0=off
    section3 = 0 #boolean 0=off


    relay_status = {'Relay-01': 'OFF', 'Relay-02': 'OFF', 'Relay-03': 'OFF', 'Relay-04': 'OFF'}
    loop_count = 0
    #time_count = 0
    max_loop_count = 0
    max_time_count = 0
    total_loop_count = 0
    loop_time = 0
    loops_left = 0


    last_state = 0
    current_state = 0

    current_wemo_state = 0

    STOP = 0

    #junk = None

    #mag sensor timestamps used for speed and safety calculations
    mag_sensor1_ts = 0
    mag_sensor2_ts = 0
    mag_sensor3_ts = 0
    mag_sensor4_ts = 0
    mag_sensor5_ts = 0

    # these values get set from a config file in the main routine
    wemo_ip = ''
    wemo_mac = ''
    #relay_wemo_ip = ''
    #relay_wemo_mac = ''
    #relay_server = ''
    #relay_server_port = ''
    log_filename = ''
    state_filename = ''
    rabbitmq_pid_file = ''
    log_level = ''

    previous_mode = 0

    
    #list_test = ['one','two','three']
    #test = ''

    '''    
    train_state_dict = {
    'power':0,#boolean 0=off
    'mode':0, #0=none, 1=loop, 2=shuttle, 3=random
    'direction':'B', #B is default direction for going around the loop
    'loops_left':0,
    'last_location':1, #last sensor to see the train 1-5
    'lights':0, #boolean 0=off
    'section1':0, #boolean 0=off
    'section2':0, #boolean 0=off
    'section3':0 #boolean 0=off
    }    
    ''' 
