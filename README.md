#Train
Trainsite is a model train automation system.
It is all written in Python and runs on a Raspberry Pi.

The system allows the train system to be controlled through a web interface.
The system uses magnetic sensors to determine where the trains are.

My trainsite is using the following hardware:
WeMo switch to turn on and off power (power supply)
GertBot Rasbperry Pi add-on board to control the motor power
Sainsmart TCP/IP 8-port relay box to turn on/off track power blocks and accessories

The primary moudules used in the project are:
Flask  (web services)
RabbitMQ/pikia (message/task queueing)
gevent (subscribe/publish web events)
RPi.GPIO (control RPi pins and such)
Ouimeaux (Belkin WeMo python program and Python library)

 
