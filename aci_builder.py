#!/usr/bin/env python
#!/usr/bin/env python
################################################################################
#                                                                                                                                  
#    Licensed under the Apache License, Version 2.0 (the "License"); you may   
#    not use this file except in compliance with the License. You may obtain   
#    a copy of the License at                                                  
#                                                                              
#         http://www.apache.org/licenses/LICENSE-2.0                           
#                                                                              
#    Unless required by applicable law or agreed to in writing, software       
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT 
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the  
#    License for the specific language governing permissions and limitations   
#    under the License.                                                        
#                                                                              
################################################################################

description = '''
    ACI Builder starts from a completly unconfigured ACI Fabric.  This script should be run imdediatly after
    the the APIC can be connected to via the API.

    This script will complete the following:
    Add All Switches to the fabric
    Configure the fabric for required admin functions
        BGP, DNS, NTP, SNMP, OOB Management (with security), syslog server, and external authentication
    Configure a VMware domain and pyhsical interfaces for ESXi hosts
    Create two Tenants with associated components
        Demo Application Profiles
        L3 Gateway
        Common Filters and Contracts


    Please comment out from main the portions of this script that you don't need.
    '''

# list of packages that should be imported for this code to work

import cobra.mit.access, cobra.mit.session
import acitoolkit.acitoolkit as ACI
import sys, os, getpass, random, string, json, requests

config_file_name = 'aci_builder_config.json'
connected = False

def error_message(error):
    '''  Calls an error message.  This takes 1 list argument with 3 components.  #1 is the error number, #2 is the error text, 
         #3 is if the application should continue or not.  Use -1 to kill the application.  Any other number
         continues the application.  You must code in a loop and go back to where you want unless you are exiting.
    '''
    
    print ('\n=================================')
    print ('  ERROR Number: ' + str(error[0]))
    print ('  ERROR Text: ' + str(error[1]))
    print ('=================================\n')
    
    if error[2] == -1:
        print ('Application ended due to error.\n')
        sys.exit()

def askInput():
    junk = raw_input('Would you like to continue?  (Yes) or No: ')
    if junk.lower() == 'no' or junk.lower() == 'n':
        exit()
    else:
        return

def create_config_file():
	try:
		config_file = open(config_file_name, 'w')
	except:
		print ('\n\nConfiguration file can not be created: ' + config_file_name + '\n\n')
		exit()

	config_file_text = '''
{
    "__comment__0": "All values in this file are strings.  Never use numbers.'",

    "credentials":  {
        "__comment__": "This information is not secure and should only be used for initial setup",
        "accessmethod": "https",
        "ip_addr": "172.31.0.0",
        "user": "admin",
        "password": "cisco"
    },

    "nodes": {
        "__comment__1": "spine and leaf refer only to the device type.  Naming is done in the specific sections.  We could add rack locations later to this section.",
        "switches" : [
            ["spine", "SAL18418V8N"],
            ["leaf", "SAL1910AL3M"],
            ["leaf", "SAL1910BL7L"]
        ],
        "spines": {
            "__comment__": "This will create names like 'Spine-101'",
            "namebase": "Spine",
            "numberbase": "101"
        },
        "leafs":  {
            "namebase": "Leaf",
            "numberbase": "201"
        }
    },

    "bgp":  {
        "__comment__": "All spines will be used as BGP route reflectors.",
        "asnum": "65001"
    },

    "oob": {
        "dg_mask": "172.31.0.1/24",
        "start_ip": "172.31.0.12",
        "end_ip": "172.31.0.19"
    },

    "time":  {
        "servers": [
            "0.pool.ntp.org",
            "1.pool.ntp.org"
        ],

        "polling":  {
            "minpoll": "4",
            "maxpoll": "6"
        }
    },

    "dns": 
        {
        "__comment__": "The first server and domain will be preferred.",
        "servers":  [
            "8.8.8.8",
            "8.8.8.7"
        ],
        "domains": [
            "c1lab.com"
        ]
    },


    "vmware_vmm":  {
        "__comment__": "namebase will be used to start the naming of everything releated to VMware",
        "namebase": "c1_lko-lab",
        "vcenterip": "172.31.0.20",
        "vlan_start": "2000",
        "vlan_end": "2099",
        "user": "administrator",
        "password": "cisco!098",
        "datacenter": "ACI_Lab"
    },

    "esxi_servers": {
        "__comment__0": "Interface speed can be 1 or 10",
        "speed": "10",
        "cdp": "enabled",
        "lldp": "disabled",
        "__comment__1": "Interface configuration will be attached to all leaf switches",
        "__comment__2": "Only a single interface statement can be used in this script",
        "__comment__3": "valid values: 1/13 or 1/22-24",
        "interfaces": "1/17-18"
    }
}
	'''
	config_file.write(config_file_text)
	config_file.close()
	print ('Configuration file created:  {0}'.format(config_file_name))

def collect_admin(config):
	if config['accessmethod'] and config['ip_addr']:
		ip_addr = config['accessmethod'] + '://' + config['ip_addr']
	else:
		ip_addr = raw_input('IP or Hostname of the APIC: ')
        
	if config['user']:
		user = config['user']
	else:
		user = raw_input('Administrative Login: ')

	if config['password']:
		password = config['password']
	else:
		password = getpass.getpass('Administrative Password: ')

	return {'ip_addr':ip_addr, 'user':user, 'password':password}

def cobra_login(admin_info):
	# log into an APIC and create a directory object
	ls = cobra.mit.session.LoginSession(admin_info['ip_addr'], admin_info['user'], admin_info['password'])
	md = cobra.mit.access.MoDirectory(ls)
	md.login()
	return md

def toolkit_login(admin_info):
    session = ACI.Session(admin_info['ip_addr'], admin_info['user'], admin_info['password'])
    response = session.login()
 
    if not response.ok:
        error_message ([1,'There was an error with the connection to the APIC.', -1])
        return False

    decoded_response = json.loads(response.text)

    if (response.status_code != 200):
        if (response.status_code == 401):
            connection_status = 'Username/Password incorrect'
            return False
        else:
            error_message ([decoded_response['imdata'][0]['error']['attributes']['code'], decoded_response['imdata'][0]['error']['attributes']['text'], -1])
            return False
    
    elif (response.status_code == 200):
        refresh = decoded_response['imdata'][0]['aaaLogin']['attributes']['refreshTimeoutSeconds']
        cookie = response.cookies['APIC-cookie']
        return session
    else:
        return False

    return False

def rest_login(admin):
    ''' Login to the system.  Takes information in a dictionary form for the admin user and password
    Will error and stop execution if it can't login. 
    Returns a ditonary for use with REST queries.  Check aci_builder_switches.py for more info on it's use.
    '''
    headers = {'Content-type': 'application/json'}
  
    login_url = '{0}/api/aaaLogin.json?gui-token-request=yes'.format(admin['ip_addr'])
    payload = '{"aaaUser":{"attributes":{"name":"' + admin['user']  + '","pwd":"' + admin['password'] + '"}}}'
  
    try:
        result = requests.post(login_url, data=payload, verify=False)
    except requests.exceptions.RequestException as error:   
        error_message ([1,'There was an error with the connection to the APIC.', -1])
 
    decoded_json = json.loads(result.text)

    if (result.status_code != 200):
        error_message ([decoded_json['imdata'][0]['error']['attributes']['code'], decoded_json['imdata'][0]['error']['attributes']['text'], -1])
    
    urlToken = decoded_json['imdata'][0]['aaaLogin']['attributes']['urlToken']
    refresh = decoded_json['imdata'][0]['aaaLogin']['attributes']['refreshTimeoutSeconds']
    cookie = result.cookies['APIC-cookie']

    admin.update({'urlToken':urlToken,'refreshTimeoutSeconds':refresh, 'APIC-cookie':cookie})

    return admin

def import_config(config_file_name):
    try:
        with open(config_file_name) as json_data:
            system_config = json.load(json_data)

    except IOError:
        print ('No config file found ({0}).  Use "aci_builder_config.py --makeconfig" to create a base file.'.format(config_file_name))
        exit()

    except:
        print ('There is a syntax error with your config file.  Please use the python interactive interpreture to diagnose. (python; import {0})'.format(config_file_name))
        exit()

    return system_config

def main(argv):
    # Supression of warnings for SSL certs and all other errors
    # f = open(os.devnull, 'w')
    # sys.stderr = f

    if len(argv) > 1:
        if argv[1] == '--makeconfig':
            create_config_file()
            exit()

    system_config = import_config(config_file_name)
    creds = system_config['credentials']

    # Login and get things going.  
    admin = collect_admin(creds)

    cobra_session = cobra_login(admin)
    acitoolkit_session = toolkit_login(admin)
    rest_session = rest_login(admin)

    print ("\nLogged into system.\n")

    # Add leafs and spines to the system
    import aci_builder_switches as Switches
    Switches.build_switches(rest_session, system_config['nodes'])

    # Configure basics of the fabric
    import aci_builder_fabric as Fabric
    Fabric.build_fabric(cobra_session, system_config)

    print ("\nAll operations completed.\n")

if __name__ == '__main__':
    main(sys.argv)