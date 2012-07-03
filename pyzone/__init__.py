#!/usr/bin/env python

import subprocess, os

CMD_ZONEADM = "/usr/sbin/zoneadm"
CMD_ZONECFG = "/usr/sbin/zonecfg"
CMD_PFEXEC = "/usr/bin/pfexec"
#from zoneadm.c
ZONE_ENTRY = {
    'ZID' :    0,
    'ZNAME' :  1,
    'ZSTATE' : 2,
    'ZROOT' : 3,
    'ZUUID' : 4,
    'ZBRAND' : 5,
    'ZIPTYPE' : 6,
#    'FM_PROFILE' : 7,
}

ZONE_STATE = {
    'running' : 0,
    'installed' : 1, # halted zone
    'configured' : 2, # not yet installed or detached zone
    'ready' : 3, # assigned id but no user process yet running
}

def getoutputs(cmd):
    """
    @param list(cmd)
    this is just a helper function
    """
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    ret = proc.returncode
    print("Executing cmd %s" % " ".join(cmd))
    if ret:
        raise OSError("%s exited with returncode %d: stderr %s stdout: %s" % (str(cmd), ret, stderr, stdout))

    return stdout


class ZoneException(Exception):
    pass

class Zone(object):
    """simple zone wrapper"""
    def __init__(self, name):
        """
        @param name - name of the zone
        """
        self.__zone_attr = {}
        self.set_zone_attr(ZONE_ENTRY['ZNAME'], name)

    def refresh_all_info(self):
        """
        Possibly all zone properties can be changed so let's refresh it asap
        """
        # Do not use uuid as it's not available in state configured
        state_cmd = [CMD_ZONEADM, "-z",
                self.get_zone_attr(ZONE_ENTRY['ZNAME']), "list",  "-p"]

        line_items = getoutputs(state_cmd).split(":")
        for val in ZONE_ENTRY.values():
            # our ZONE_MAPING reflects __zone_attr
            self.__zone_attr[val] = line_items[val]

    def set_zone_attr(self, attr, value):
        if attr in ZONE_ENTRY.values():
            self.__zone_attr[int(attr)] = value
        else:
            raise ZoneException("Unsupported ZONE_ENTRY attribute: %s." %
                            str(attr))

    def get_zone_attr(self, attr, fallback=None):
        try:
            return self.__zone_attr[attr]
        except KeyError:
            return fallback

    #--------------------------------------------------------------------------
    # wrapped get_zone_attr calls
    #--------------------------------------------------------------------------
    def get_zonepath(self):
        """
        returns an integer reprezenting state in ZONE_STATE
        """
        return self.__zone_attr[ZONE_ENTRY['ZROOT']]

    def get_state(self):
        """
        returns an integer reprezenting state in ZONE_STATE
        please call refresh_all_info() before calling get_state()
        """
        return ZONE_STATE[self.__zone_attr[ZONE_ENTRY['ZSTATE']]]

    def get_brand(self):
        """
        returns brand of the zone
        """
        return self.__zone_attr[ZONE_ENTRY['ZBRAND']]

    def get_name(self):
        """
        returns zone name as listed by zoneadm list -pc
        """
        return self.__zone_attr[ZONE_ENTRY['ZNAME']]

    #--------------------------------------------------------------------------
    # Changing state of Zones
    #--------------------------------------------------------------------------

    def __zone_in_states(self, state_list):
        if self.get_state() not in state_list:
            raise ZoneException("Zone must be in one of states: %s." % str(state_list))

    def boot(self):
        self.__zone_in_states((ZONE_STATE['installed'],))
        boot_cmd = [CMD_PFEXEC , CMD_ZONEADM, "-z", self.get_name(), "boot"]
        getoutputs(boot_cmd)

    def shutdown(self):
        self.__zone_in_states((ZONE_STATE['running'],))
        shutdown_cmd = [CMD_PFEXEC , CMD_ZONEADM, "-z", self.get_name(), "shutdown"]
        getoutputs(shutdown_cmd)

    def halt(self):
        self.__zone_in_states((ZONE_STATE['running'],))
        halt_cmd = [CMD_PFEXEC , CMD_ZONEADM, "-z", self.get_name(), "halt"]
        getoutputs(halt_cmd)

    def reboot(self):
        self.__zone_in_states((ZONE_STATE['running'],))
        reboot_cmd = [CMD_PFEXEC , CMD_ZONEADM, "-z", self.get_name(), "shutdown", "-r"]
        getoutputs(reboot_cmd)

    #--------------------------------------------------------------------------
    # Install
    #--------------------------------------------------------------------------
    def install(self):
        install_cmd = [CMD_PFEXEC, CMD_ZONEADM, "-z", self.get_name(),
                "install"]
        getoutputs(install_cmd)
        # TBD post install configuration

    #--------------------------------------------------------------------------
    # Deletion / Creation
    #--------------------------------------------------------------------------
    def exists(self):
        get_zone_by_name(self.get_name())

    def create(self):
        self._create_minimal() # Let's create a zone with minimal config first
        brand = self.get_brand()
        if brand in ("solaris10", "solaris"):
            self._zonecfg_set("brand", brand)

    def _zonecfg_set(self, attr, value):
        cmd_base = [CMD_PFEXEC, CMD_ZONECFG, "-z", self.get_name()]
        cmd_base.append("set %s=%s;exit" % (str(attr), str(value)))
        getoutputs(cmd_base)

    def _create_minimal(self):
        """
        minimal form of the creation command
        """
        cmd_base = ["pfexec", CMD_ZONECFG, "-z", self.get_name()]
        minimal_config = ["create","set zonepath=%s" % self.get_zonepath(),
                "exit"]
        cmd_base.append(";".join(minimal_config))
        getoutputs(cmd_base)

    def delete(self):
        self.__zone_in_states(ZONE_STATE['configured'],)
        del_cmd = ["pfexec", CMD_ZONECFG, "-z", self.get_name(), "delete", "-F"]
        getoutputs(del_cmd)

def get_zone_by_name(zname):
    """
    returns Zone() instance
    """
    for zone in list_zones():
        if zone.get_name() == zname:
            return zone

    return None

def list_zones():
    """
    returns list of Zone() instances representing configured zones
    """
    zlist = []
    cmd = [CMD_ZONEADM, "list",  "-pc"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    ret = proc.returncode

    if ret:
        raise OSError("%s exited with exit code %d. stderr: '%s.'" %
            (str(cmd), ret, stderr))

    def set_zone_attr(zone, attr, line):
        zone.set_zone_attr(attr, line[attr])

    # line format:
    # zoneid:zonename:state:zonepath:uuid:brand:ip-type:r/w:file-mac-profile
    for line in stdout.split("\n"):
        if not line:
            continue
        line = line.split(":")
        # zoneid + state can be ignored as these are not static values
        tmp_zone = Zone(line[ZONE_ENTRY['ZNAME']])
        for item in ZONE_ENTRY.values():
            set_zone_attr(tmp_zone, item, line)

        zlist.append(tmp_zone)


    return zlist
