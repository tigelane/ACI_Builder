#!/usr/bin/env python
################################################
#   ________         .____          ___.       #
#  /  _____/  ____   |    |   _____ \_ |__     #
# /   \  ___ /  _ \  |    |   \__  \ | __ \    #
# \    \_\  (  <_> ) |    |___ / __ \| \_\ \   #
#  \______  /\____/  |_______ (____  /___  /   #
#         \/                 \/    \/    \/    #
################################################################################
#                                                                              #                                                      
#    Licensed under the Apache License, Version 2.0 (the "License"); you may   #
#    not use this file except in compliance with the License. You may obtain   #
#    a copy of the License at                                                  #
#                                                                              #
#         http://www.apache.org/licenses/LICENSE-2.0                           #
#                                                                              #
#    Unless required by applicable law or agreed to in writing, software       #
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT #
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the  #
#    License for the specific language governing permissions and limitations   #
#    under the License.                                                        #
#                                                                              #
################################################################################
description = '''
    This script will create and push a configuration for an ACI lab.  
    This will include the following:
    * BGP route reflector policy using all spines as route reflectors.
    * OOB Management interfaces and addresses from a range
    * NTP configuration
    * DNS configuration

    Please modify go_lab_config.py to suit your environment. 

    datacenter/WebArya on github was primarily used to build the calls to the APIC.
'''

# list of packages that should be imported for this code to work
import cobra.mit.access
import cobra.mit.session
import cobra.mit.request
import cobra.model.bgp
import cobra.model.pol
import cobra.model.fabric
import cobra.model.datetime
import cobra.model.mgmt
import cobra.model.infra
import cobra.model.fvns
import cobra.model.dns
from cobra.internal.codec.xmlcodec import toXMLStr

import go_utils
import sys, getpass, random, string

def hello_message():
    print "\nPlease be cautious with this application.  The author did very little error checking and can't ensure it will work as expected.\n"
    print description
    junk = raw_input('Press Enter/Return to continue.')
    return
    
def collect_admin_info():

    if go_lab_config.credentials['accessmethod'] and go_lab_config.credentials['ip_addr']:
        ip_addr = go_lab_config.credentials['accessmethod'] + '://' + go_lab_config.credentials['ip_addr']
    else:
        ip_addr = raw_input('URL of the APIC: ')
        
    if go_lab_config.credentials['user']:
        user = go_lab_config.credentials['user']
    else:
        user = raw_input('Administrative Login: ')

    if go_lab_config.credentials['password']:
    	password = go_lab_config.credentials['password']
    else:
    	password = getpass.getpass('Administrative Password: ')
    
    return [ip_addr, user, password]

def login(ip_addr, user, password):
	# log into an APIC and create a directory object
	ls = cobra.mit.session.LoginSession(ip_addr, user, password)
	md = cobra.mit.access.MoDirectory(ls)
	md.login()
	return md

def create_bgp(md):
	asnum = go_lab_config.bgp['asnum']
	switches = []

	if go_lab_config.spines['numberbase'] and go_lab_config.spines['totalnumber']:
		firstnumber = int(go_lab_config.spines['numberbase'])
		totalnumber = int(go_lab_config.spines['totalnumber'])
		for a in range(0, totalnumber):
			switches.append(str(firstnumber + a))

		polUni = cobra.model.pol.Uni('')
		fabricInst = cobra.model.fabric.Inst(polUni)

		bgpInstPol = cobra.model.bgp.InstPol(fabricInst, ownerKey=u'', name=u'default', descr=u'', ownerTag=u'')
		bgpRRP = cobra.model.bgp.RRP(bgpInstPol, name=u'', descr=u'')

		for spine_number in switches:
			bgpRRNodePEp = cobra.model.bgp.RRNodePEp(bgpRRP, id=spine_number, descr=u'')
		bgpAsP = cobra.model.bgp.AsP(bgpInstPol, asn=asnum, descr=u'', name=u'')

		c = cobra.mit.request.ConfigRequest()
		c.addMo(polUni)
		md.commit(c)

def create_oob_policy(md):
    if not create_oob_ipPool(md):
     	return False
    if not create_oob_connGroup(md):
     	return False
    if not create_oob_nodeMgmt(md):
    	return False

def create_oob_ipPool(md):
	dg_mask = go_lab_config.oob['dg_mask']
	start_ip = go_lab_config.oob['start_ip']
	end_ip = go_lab_config.oob['end_ip']

	polUni = cobra.model.pol.Uni('')
	fvTenant = cobra.model.fv.Tenant(polUni, 'mgmt')

	fvnsAddrInst = cobra.model.fvns.AddrInst(fvTenant, ownerKey=u'', addr=dg_mask, descr=u'', skipGwVal=u'no', ownerTag=u'', name=u'Switch-OOB_addrs')
	fvnsUcastAddrBlk = cobra.model.fvns.UcastAddrBlk(fvnsAddrInst, to=end_ip, from_=start_ip, name=u'', descr=u'')

	c = cobra.mit.request.ConfigRequest()
	c.addMo(polUni)
	md.commit(c)
	return True

def create_oob_connGroup(md):
	polUni = cobra.model.pol.Uni('')
	infraInfra = cobra.model.infra.Infra(polUni)
	infraFuncP = cobra.model.infra.FuncP(infraInfra)

	mgmtGrp = cobra.model.mgmt.Grp(infraFuncP, name=u'Switch-OOB_conngrp')
	mgmtOoBZone = cobra.model.mgmt.OoBZone(mgmtGrp, name=u'', descr=u'')
	mgmtRsAddrInst = cobra.model.mgmt.RsAddrInst(mgmtOoBZone, tDn=u'uni/tn-mgmt/addrinst-Switch-OOB_addrs')
	mgmtRsOobEpg = cobra.model.mgmt.RsOobEpg(mgmtOoBZone, tDn=u'uni/tn-mgmt/mgmtp-default/oob-default')

	c = cobra.mit.request.ConfigRequest()
	c.addMo(polUni)
	md.commit(c)

	return True

def create_oob_nodeMgmt(md):
	switches = []
	
	# Build a list of switches to add to the OOB Management network
	if go_lab_config.leafs['numberbase'] and go_lab_config.leafs['totalnumber']:
		firstnumber = int(go_lab_config.leafs['numberbase'])
		totalnumber = int(go_lab_config.leafs['totalnumber'])
		for a in range(0, totalnumber):
			switches.append(str(firstnumber + a))

	if go_lab_config.spines['numberbase'] and go_lab_config.spines['totalnumber']:
		firstnumber = int(go_lab_config.spines['numberbase'])
		totalnumber = int(go_lab_config.spines['totalnumber'])
		for a in range(0, totalnumber):
			switches.append(str(firstnumber + a))



	polUni = cobra.model.pol.Uni('')
	infraInfra = cobra.model.infra.Infra(polUni)

	mgmtNodeGrp = cobra.model.mgmt.NodeGrp(infraInfra, ownerKey=u'', name=u'Switch-OOB_nodes', ownerTag=u'', type=u'range')
	mgmtRsGrp = cobra.model.mgmt.RsGrp(mgmtNodeGrp, tDn=u'uni/infra/funcprof/grp-Switch-OOB_conngrp')

	for switch in switches:
		names = [random.choice(string.hexdigits).lower() for n in xrange(16)]
		name = ''.join(names)
		infraNodeBlk = cobra.model.infra.NodeBlk(mgmtNodeGrp, from_=switch, name=name, to_=switch)

	c = cobra.mit.request.ConfigRequest()
	c.addMo(polUni)
	md.commit(c)

	return True

def create_pod_policy(md):
	polUni = cobra.model.pol.Uni('')
	fabricInst = cobra.model.fabric.Inst(polUni)
	fabricFuncP = cobra.model.fabric.FuncP(fabricInst)

	# build the request using cobra syntax
	fabricPodPGrp = cobra.model.fabric.PodPGrp(fabricFuncP, ownerKey=u'', name=u'PodPolicy', descr=u'', ownerTag=u'')
	fabricRsPodPGrpBGPRRP = cobra.model.fabric.RsPodPGrpBGPRRP(fabricPodPGrp, tnBgpInstPolName=u'default')
	fabricRsTimePol = cobra.model.fabric.RsTimePol(fabricPodPGrp, tnDatetimePolName=u'default')

	# Feel free to uncomment if any of these are needed.
	# fabricRsSnmpPol = cobra.model.fabric.RsSnmpPol(fabricPodPGrp, tnSnmpPolName=u'')
	# fabricRsCommPol = cobra.model.fabric.RsCommPol(fabricPodPGrp, tnCommPolName=u'')
	# fabricRsPodPGrpCoopP = cobra.model.fabric.RsPodPGrpCoopP(fabricPodPGrp, tnCoopPolName=u'')
	# fabricRsPodPGrpIsisDomP = cobra.model.fabric.RsPodPGrpIsisDomP(fabricPodPGrp, tnIsisDomPolName=u'')

	c = cobra.mit.request.ConfigRequest()
	c.addMo(polUni)
	md.commit(c)

def create_pod_policy_profile(md):
	polUni = cobra.model.pol.Uni('')
	fabricInst = cobra.model.fabric.Inst(polUni)
	fabricPodP = cobra.model.fabric.PodP(fabricInst, 'default')

	fabricPodS = cobra.model.fabric.PodS(fabricPodP, ownerKey=u'', name=u'default', descr=u'', ownerTag=u'', type=u'ALL')
	fabricRsPodPGrp = cobra.model.fabric.RsPodPGrp(fabricPodS, tDn=u'uni/fabric/funcprof/podpgrp-PodPolicy')

	c = cobra.mit.request.ConfigRequest()
	c.addMo(polUni)
	md.commit(c)

def create_time_policy(md):
	minpoll = go_lab_config.time['minpoll']
	maxpoll = go_lab_config.time['maxpoll']
	servers = []
	for a in range(0, 10):
		server = 'server' + str(a)
		try:
			if go_lab_config.time[server]:
				servers.append(go_lab_config.time[server])
		except:
			pass

	polUni = cobra.model.pol.Uni('')
	fabricInst = cobra.model.fabric.Inst(polUni)
	datetimePol = cobra.model.datetime.Pol(fabricInst, ownerKey=u'', name=u'default', descr=u'', adminSt=u'enabled', authSt=u'disabled', ownerTag=u'')
	for server in servers:
		datetimeNtpProv = cobra.model.datetime.NtpProv(datetimePol, maxPoll=maxpoll, keyId=u'0', name=server, descr=u'', preferred=u'no', minPoll=minpoll)
	
	datetimeRsNtpProvToEpg = cobra.model.datetime.RsNtpProvToEpg(datetimeNtpProv, tDn=u'uni/tn-mgmt/mgmtp-default/oob-default')

	c = cobra.mit.request.ConfigRequest()
	c.addMo(polUni)
	md.commit(c)

def create_dns_profile(md):
	server_pref = 'yes'
	search_def = 'yes'
	servers = []
	searches = []

	for a in range(0, 10):
		server = 'server' + str(a)
		search = 'search' + str(a)
		try:
			if go_lab_config.dns[server]:
				servers.append(go_lab_config.dns[server])
		except:
			pass
		try:
			if go_lab_config.dns[server]:
				searches.append(go_lab_config.dns[search])
		except:
			pass

	polUni = cobra.model.pol.Uni('')
	fabricInst = cobra.model.fabric.Inst(polUni)

	dnsProfile = cobra.model.dns.Profile(fabricInst, ownerKey=u'', name=u'default', descr=u'', ownerTag=u'')
	dnsRsProfileToEpg = cobra.model.dns.RsProfileToEpg(dnsProfile, tDn=u'uni/tn-mgmt/mgmtp-default/oob-default')
	for server in servers:
			dnsProv = cobra.model.dns.Prov(dnsProfile, addr=server, preferred=server_pref, name=u'')
			server_pref = 'no'	
	for search in searches:
			dnsDomain = cobra.model.dns.Domain(dnsProfile, isDefault=search_def, descr=u'', name=search)
			search_def = 'no'

	c = cobra.mit.request.ConfigRequest()
	c.addMo(polUni)
	md.commit(c)



	polUni = cobra.model.pol.Uni('')
	fvTenant = cobra.model.fv.Tenant(polUni, 'mgmt')
	fvCtx = cobra.model.fv.Ctx(fvTenant, ownerKey=u'', name=u'oob', descr=u'', knwMcastAct=u'permit', ownerTag=u'', pcEnfPref=u'enforced')
	dnsLbl = cobra.model.dns.Lbl(fvCtx, ownerKey=u'', tag=u'yellow-green', name=u'default', descr=u'', ownerTag=u'')


	c = cobra.mit.request.ConfigRequest()
	c.addMo(polUni)
	md.commit(c)

def askInput():
    junk = raw_input('Would you like to continue?  (Yes) or No: ')
    if junk.lower() == 'no' or junk.lower() == 'n':
        exit()
    else:
        return

def main(argv):
    hello_message()
    if len(argv) > 1:
        if argv[1] == '--makeconfig':
            go_utils.create_configfile()
            exit()
    try:
        global go_lab_config
        import go_lab_config
    except ImportError:
        print ('No config file found (go_lab_config.py).  Use "go_lab.py --makeconfig" to create a base file.')
        exit()
    except:
            print ('There is a syntax error with your config file.  Please use the python interactive interpreture to diagnose. (python; import go_lab_config)')
            exit()

    # Login and get things going.  Use 'md' as our session.
    admin = collect_admin_info()
    md = login(admin[0],admin[1],admin[2])
    print ("Logged into system.")
    create_bgp(md)
    print ("Created internal BGP routing.")
    askInput()
    create_oob_policy(md)
    print ("Created OOB Management with given IP Addresses.")
    askInput()
    create_time_policy(md)
    print ("Created NTP Policy.")
    askInput()
    create_pod_policy(md)
    print ("Created fabric pod policy for linkage.")
    askInput()
    create_pod_policy_profile(md)
    print ("Applied NTP and BGP policies to the system.")
    askInput()
    create_dns_profile(md)
    print ("Created DNS config and applied it.")

    print "\nOk, that's it.  I'm all done."

if __name__ == '__main__':
    main(sys.argv)