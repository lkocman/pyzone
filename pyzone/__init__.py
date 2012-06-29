#!/usr/bin/env python

import subprocess, os

CMD_ZONEADM="/usr/sbin/zoneadm"
CMD_ZONECFG="/usr/sbin/zonecfg"

# zoneadm list fields
F_ZONEID = 0
F_ZONENAME = 1
F_STATE = 2
F_ZONEPATH = 3
F_UUID = 4
F_BRAND = 5
F_IP_TYPE = 6
F_FM_PROFILE = 7


def getoutputs(cmd):
    """
    @param list(cmd)
    this is just a helper function
    """
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    ret = proc.returncode
    if ret:
        raise OSError("%s exited with returncode %d: %s" % (str(cmd), ret, stderr))

    return stdout


class ZoneException(Exception):
    pass

class Zone(object):
    def __init__(self, name, zonepath = None):
        """
        @param name - name of the zone
        @raise ZoneException in case that zone with given name already exist
        """
        self.__name = name

    # setters/getters
    def get_state(self):
        state_cmd = [CMD_ZONEADM, "-u", self.get_uuid(), "list",  "-p"]
        # zoneid:zonename:state:zonepath:uuid:brand:ip-type:r/w:file-mac-profile
        line_items = getoutputs(state_cmd).split(":")
        state = line_items[F_STATE]
        return state

    def get_name(self):
        return self.__name

    def set_zonepath(self, path):
        """
        @param path - abs path to zone root
        """
        if not path.startswith(os.path.sep):
            raise ZoneException("zonepath must start with %s" % os.path.sep)

        self.__zone_path =  path

    def get_zonepath(self):
        return self.__zone_path


    def _set_uuid(self, uuid):
        """
        @param uuid - zone unique id
        This should be used only during list_zones()
        """
        self.__uuid = uuid

    def get_uuid(self):
        return self.__uuid

    def set_brand(self, brand="solaris"):
        """
        @param brand - "solaris" by default
        """
        self.__brand = brand

    def get_brand(self):
        return self.__brand

    def set_ip_type(self, ip_type):
        """
        @param ip_type
        """
        self.__ip_type = ip_type

    def get_ip_type(self):
        return self.__ip_type

    def set_fm_profile(self, profile):
        """
        @param profile - file mac profile
        """
        self.__fm_profile = profile

    def get_fm_profile():
        return self.__fm_profile

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

    # line format:
    # zoneid:zonename:state:zonepath:uuid:brand:ip-type:r/w:file-mac-profile
    for line in stdout.split("\n"):
        if not line:
            continue
        line = line.split(":")
        # zoneid + state can be ignored as these are not static values
        tmp_zone = Zone(line[F_ZONENAME])
        tmp_zone.set_zonepath(line[F_ZONEPATH])
        tmp_zone._set_uuid(line[F_UUID])
        tmp_zone.set_brand(line[F_BRAND])
        tmp_zone.set_ip_type(line[F_IP_TYPE])
        tmp_zone.set_fm_profile(line[F_FM_PROFILE])
        zlist.append(tmp_zone)


    return zlist
