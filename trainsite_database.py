#!/home/mrrad/trainsite/bin/python
# python functions for using SQLalchemy with a SQlite3 database

# Provides methods for retriving, updating and deleting configuration and state info
#
# Converts a config object to a database
# None type is not allowed
# dicts are changed to JSON strings
# lists are changed to JSON strings


from __future__ import print_function
import os
import sys
import time
import random
import logging
import json
import re
import threading
from global_variables import *
from typing import List
from typing import Optional
from sqlalchemy import Column, Integer, Boolean, String
from sqlalchemy import create_engine, text, MetaData
from sqlalchemy.orm import Session, DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

        

class TrainDatabaseClass():
    _instance = None #class variable to store the single instance
    _echo = False  #to echo SQL or not
    #_DB_URL = "sqlite+pysqlite:///:memory:"
    _DB_URL = "sqlite:////home/mrrad/trainsite/traindata.db"
    
    class Base(DeclarativeBase):
        pass
        
        
    class TrainData(Base):
        __tablename__ = "traindata"
        id = Column(Integer, primary_key=True)
        name = Column(String, unique=True, nullable=False, index=True)   #the variable name
        value = Column(String, nullable=False)  #the value of the variable
        type = Column(String, nullable=False)   #the type of variable
    
        def __repr__(self) -> str:
            return f"Item(id={self.id!r} name={self.name!r} value={self.value!r}  type={self.type!r} "
        
   
    #override the new method to make this a singleton class
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
        
    
    def __init__(self,echo=False):
        self._echo=echo
        # Create the tables in the database (if they don't exist)
        self.engine = create_engine(self._DB_URL, echo=self._echo)  
        
                
        self.Base.metadata.create_all(self.engine)
        self.local_session = sessionmaker(autoflush=False, autocommit=False, bind=self.engine)
        self.db = self.local_session()
        
        #self.db.execute("PRAGMA journal_mode=PERSIST;")
        #self.db.commit()
        
        #self.lock = threading.Lock()
    
    def __del__(self):
        self.db.close()
        #print("Object destroyed.")
        
    
    def delete_record(self,name):
        ''' Deletes a record in the database based on name '''    
        #first retrieve the record based on name
        record = self.retrieve_record(name)
        
        if record is not None:
            #logging.debug("Waiting for a lock...")
            #self.lock.acquire()
            self.db.delete(record)
            self.db.commit()
            #logging.debug("Releasing the lock...")    
            #self.lock.release()
            return True
        else:
            return False
        
    
    def update_record(self,name, value):
        ''' Updates a record in the database based on name '''
        print(f"Updating {name} to  {value}")
        
        #first retrieve the record based on name
        record = self.retrieve_record(name)
        
        if record is not None:
            #logging.debug("Waiting for a lock...")
            #self.lock.acquire()
            attr_type = type(value)
            type_list = str(attr_type).split("\'")
            type_string = type_list[1]
            #print(type_string)
            
            #None type is not allowed
            if value is None:
                print(f"Type of None is not allowed for:  {name}")
                return False 
            
            if attr_type is dict:
                print(f"Type of dict is not allowed for:  {name}, converting to JSON string.")
                value = json.dumps(value)
                type_string = 'json_string'
                
                            
            if attr_type is list:
                print(f"Type of list is not allowed for:  {name}, converting to JSON string.")
                value = json.dumps(value)
                type_string = 'json_string'
            
            #update the type and value of the record    
            record.value = value
            record.type = type_string
            
            self.db.commit()   
            
            #logging.debug("Releasing the lock...")    
            #self.lock.release()
        
            return True
        else:
            return False
            
        
    def get_item(self,name):
        ''' Get an item from the database and return its value in original form '''
        #first retrieve the record based on name
        record = self.retrieve_record(name)
        
        if record is not None:
            record_name = record.name
            record_type = record.type
            record_value = record.value
            
            if record_type == "json_string":
                record_value = json.loads(record.value)
            elif record_type == "int":
                record_value = int(record.value)
            elif record_type == "float":
                record_value = float(record.value)
            elif record_type == "string":
                record_value = str(record.value)
            
            return record_value
        return None   
        
        
    def retrieve_record(self,name):
        ''' Retrieve a single record based on name.  Returns None if not found. '''
        ''' does no formatting for the type of data! '''
        #print(f"Retrieving: {name}")
        record = self.db.query(self.TrainData).filter_by(name=name).first()
        #print(f"Record: {record}")
        return record
        
        
    def retrieve_all(self):
        all_items = self.db.query(self.TrainData).all()  #returns a bunch of objects
        for item in all_items:
            print(f"Name: {item.name}  Type: {item.type}  Value: {item.value}") 
    
    
    def load_data(self,ConfigData):
        ''' Loads data into the database from a config file '''
        ''' This should only be needed for the initial load '''
        print("Loading config data into the database.")
        
        print(f"Config: {ConfigData.config_file}")
    
        variables = dir(ConfigData)
        variables = [attr for attr in dir(ConfigData) if not callable(getattr(ConfigData, attr))  and not attr.startswith('__')   ]
        #print(dir(ConfigData))
        print(variables)
        
        for item in variables:
            #print(f"Name: {item}  Value:  ")  
            #fullitem = "ConfigData." + item
            #print(f"FullItem: {fullitem} Type: {type(fullitem)}")
            value = getattr(ConfigData, item)
            attr_type = type(getattr(ConfigData, item))
            type_list = str(attr_type).split("\'")
            type_string = type_list[1]
            
            #print(f"Type_string: {type_string}")
            
            
            print(f"Name: {item}   Value = {value}  Type: {type_list[1]} ")
            
            #post = TrainData(name="mike", value='junk')
            
            #None type is not allowed
            if value is None:
                print(f"Type of None is not allowed for:  {item}")
                continue 
            
            if attr_type is dict:
                print(f"Type of dict is not allowed for:  {item}, converting to JSON string.")
                value = json.dumps(value)
                type_string = 'json_string'
                
                            
            if attr_type is list:
                print(f"Type of list is not allowed for:  {item}, converting to JSON string.")
                value = json.dumps(value)
                type_string = 'json_string'
                
            post = self.TrainData(name=item, value=value, type=type_string)
            self.db.add(post)
            
        self.db.commit() #faster to just do 1 commit
    
    

##### MAIN SECTION #####################
if __name__ == "__main__":
    print("Running SQLalchemy tests.", file=sys.stderr)

    
    
    TrainDatabase = TrainDatabaseClass(False)
    
    ConfigData = SharedData()
    
    #TrainDatabase.load_data(ConfigData)
    
    #TrainDatabase.retrieve_all()
    
    item = TrainDatabase.retrieve_record("list_test")
    if item is not None:
        if item.type == 'json_string':
            value = json.loads(item.value)  #make it a json object again
            print(f"Type of item: {type(value)}")
        print(f"Name: {item.name}  Type: {item.type} Value: {item.value}")
    else:
        print(f"Item not found!")
    
    value = TrainDatabase.get_item("power")
    print(f"Value from get_item is  {value}   Type is: {type(value)}")
    
    
    result = TrainDatabase.update_record("test","good")
    
    #TrainDatabase.retrieve_all()
    
    result = TrainDatabase.delete_record("test")
    if result:
        print("Record was deleted.")
        
    #TrainDatabase.retrieve_all()
    
    del TrainDatabase
    
    
