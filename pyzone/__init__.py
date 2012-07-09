#!/usr/bin/env python

"""
pyzone - a simple module for managing Solaris Zones
"""
import subprocess, os, re

CMD_ZONEADM = "/usr/sbin/zoneadm"
CMD_ZONECFG = "/usr/sbin/zonecfg"
CMD_ZLOGIN  = "/usr/sbin/zlogin"
CMD_PFEXEC  = "/usr/bin/pfexec"

# zoneadm.c ZONE_ENTRY like structure
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

class ZoneException(Exception):
    """General zone exception"""
    pass

class PrivilegesError(Exception):
    """
    Exception signalizing that user does not have required permissions
    """
    pass

def check_user_permissions(profiles=("Primary Administrator",
                            "Zone Management")):
    """
    this function is being used to check wheather the user is capable of executing
    zone* commands

    @param - profiles list of profiles to match. Default:
             ["Primary Administrator", "Zone Management"]

    @raise - PrivilegeError in case that none of profiles is being listed by
             profiles(1)
    """

    if os.uname()[0] == "SunOS" and profiles:
        profiles_output = getoutputs(["profiles", ], False)
        for line in str(profiles_output).split("\n"):
            line = line.strip()
            if line in profiles:
                return

    # last chance the root
    if os.getuid() == 0:
        return

    raise PrivilegesError("Not enough privileges to perform action.")


def getoutputs(cmd, check_privileges=True):
    """
    @param list(cmd)
    @param check_privileges=True - checking uid and user roles (zones only)
    @raise: OSError in case of non-zero returncode (Except of permissions issue)
    """

    if check_privileges:
        check_user_permissions()

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    ret = proc.returncode
    if ret:
        raise OSError("%s exited with returncode %d: stderr %s stdout: %s" %
                (str(cmd), ret, stderr, stdout))
    return stdout

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

        line_items = str(getoutputs(state_cmd)).split(":")
        for val in ZONE_ENTRY.values():
            # our ZONE_MAPING reflects __zone_attr
            self.__zone_attr[val] = line_items[val]

    def set_zone_attr(self, attr, value):
        """
        sets zone attribute
        @param attr - integer value from ZONE_ENTRY
        @param value - value

        Note: for now set_zone_attr takes effect only on zone creation
        """
        if attr in ZONE_ENTRY.values():
            self.__zone_attr[int(attr)] = value
        else:
            raise ZoneException("Unsupported ZONE_ENTRY attribute: %s." %
                            str(attr))

    def get_zone_attr(self, attr, fallback=None):
        """
        returns zone attribute
        @param attr - integer value from ZONE_ENTRY
        """
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
        """
        @param state_list list of ZONE_STATE values
        @raise ZoneException in case that zone.get_state does not match
               any value in state_list
        """
        if self.get_state() not in state_list:
            raise ZoneException("Zone must be in one of states: %s." %
                    str(state_list))

    def boot(self):
        """
        note: RBAC aware (pfexec and roles check)
        """
        check_user_permissions()

        self.__zone_in_states((ZONE_STATE['installed'],))
        boot_cmd = [CMD_PFEXEC , CMD_ZONEADM, "-z", self.get_name(), "boot"]
        getoutputs(boot_cmd)


    def ready(self):
        """
        note: RBAC aware (pfexec and roles check)
        """
        check_user_permissions()

        self.__zone_in_states((ZONE_STATE['installed'],))
        ready_cmd = [CMD_PFEXEC, CMD_ZONEADM, "-z", self.get_name(), "ready"]
        getoutputs(ready_cmd)

    def shutdown(self):
        """
        note: RBAC aware (pfexec and roles check)
        """
        check_user_permissions()

        self.__zone_in_states((ZONE_STATE['running'],))
        shutdown_cmd = [CMD_PFEXEC , CMD_ZONEADM, "-z", self.get_name(),
                "shutdown"]
        getoutputs(shutdown_cmd)

    def halt(self):
        """
        note: RBAC aware (pfexec and roles check)
        """
        check_user_permissions()

        self.__zone_in_states((ZONE_STATE['running'],))
        halt_cmd = [CMD_PFEXEC , CMD_ZONEADM, "-z", self.get_name(), "halt"]
        getoutputs(halt_cmd)

    def reboot(self):
        """
        note: RBAC aware (pfexec and roles check)
        """
        check_user_permissions()

        self.__zone_in_states((ZONE_STATE['running'],))
        reboot_cmd = [CMD_PFEXEC , CMD_ZONEADM, "-z", self.get_name(),
                "shutdown", "-r"]
        getoutputs(reboot_cmd)

    #--------------------------------------------------------------------------
    # Install
    #--------------------------------------------------------------------------
    def install(self):
        """
        note: RBAC aware (pfexec and roles check)
        """
        check_user_permissions()

        self.__zone_in_states((ZONE_STATE['configured'],))

        install_cmd = [CMD_PFEXEC, CMD_ZONEADM, "-z", self.get_name(),
                "install"]
        getoutputs(install_cmd)
        # TBD post install configuration

    #--------------------------------------------------------------------------
    # Deletion / Creation
    #--------------------------------------------------------------------------
    def exists(self):
        """
        function returns True in case that zone already exist otherwise 
        false is returned
        """
        return get_zone_by_name(self.get_name())

    def create(self):
        """
        creates a zone from given configuration
        """
        self._create_minimal() # Let's create a zone with minimal config first
        brand = self.get_brand()

        if brand in ("solaris10", "solaris"):
            self._zonecfg_set("brand", brand)

    def _zonecfg_set(self, attr, value):
        """
        note: RBAC aware (pfexec and roles check)
        @param attr - attribute a string e.g. zonepath
        @param value - value
        """
        check_user_permissions()
        cmd_base = [CMD_PFEXEC, CMD_ZONECFG, "-z", self.get_name()]
        cmd_base.append("set %s=%s;exit" % (str(attr), str(value)))
        getoutputs(cmd_base)

    def _create_minimal(self):
        """
        minimal form of the creation command:
        Note: RBAC aware (pfexec and roles check)
        """
        check_user_permissions()
        cmd_base = ["pfexec", CMD_ZONECFG, "-z", self.get_name()]
        minimal_config = ["create","set zonepath=%s" % self.get_zonepath(),
                "exit"]
        cmd_base.append(";".join(minimal_config))
        getoutputs(cmd_base)

    def delete(self):
        """
        Note: RBAC aware (pfexec and roles check)
        """
        check_user_permissions()
        self.__zone_in_states(ZONE_STATE['configured'],)
        del_cmd = ["pfexec", CMD_ZONECFG, "-z", self.get_name(), "delete", "-F"]
        getoutputs(del_cmd)

    #--------------------------------------------------------------------------
    # Remote execution
    #--------------------------------------------------------------------------

    def execute(self, cmd, user="root"):
        """
        uses zlogin to execute a command
        Note: RBAC aware (pfexec and roles check)
        @param cmd - a string representing command + args
        @param user - zone user default is root

        returns stdout

        function uses getoutputs()
        @raise OSError if returncode != 0
        @raise PrivilegesError in case of missing privileges
        """
        #zlogin [ -dCES ] [ -e cmdchar ] [-l user] zonename [command [args ...]]
        zlogin_cmd = [CMD_ZLOGIN]

        if user:
            zlogin_cmd.append("-l %s" % user)

        zlogin_cmd.append(self.get_name())
        zlogin_cmd.append("%s" % str(cmd))

        zlogin_cmd = " ".join(zlogin_cmd)
        getoutputs(zlogin_cmd)


def get_zone_by_name(zname):
    """
    returns Zone() instance
    """
    for zone in list_zones():
        if zone.get_name() == zname:
            return zone

    return None

def list_zones(pattern=None):
    """
    returns list of Zone() instances representing configured zones
    @param pattern - pattern passed to re.match which filters zone names
    """
    zlist = []
    cmd = [CMD_ZONEADM, "list",  "-pc"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    ret = proc.returncode

    if ret:
        raise OSError("%s exited with exit code %d. stderr: '%s.'" %
            (str(cmd), ret, stderr))

    def set_attr(zone, attr, line):
        """just a helper function """
        zone.set_zone_attr(attr, line[attr])

    # line format:
    # zoneid:zonename:state:zonepath:uuid:brand:ip-type:r/w:file-mac-profile
    for line in str(stdout).split("\n"):
        if not line:
            continue
        line = line.split(":")

        if pattern and not(re.match(pattern, line[ZONE_ENTRY['ZNAME']])):
            continue # skip entries that does not pass regexp

        tmp_zone = Zone(line[ZONE_ENTRY['ZNAME']])
        for item in ZONE_ENTRY.values():
            set_attr(tmp_zone, item, line)

        zlist.append(tmp_zone)


    return zlist
