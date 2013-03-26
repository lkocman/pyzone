#!/usr/bin/env python

"""
pyzone - a simple module for managing Solaris zones
"""
import subprocess, os, re

CMD_ZONEADM = "/usr/sbin/zoneadm"
CMD_ZONECFG = "/usr/sbin/zonecfg"
CMD_ZLOGIN  = "/usr/sbin/zlogin"
CMD_PFEXEC  = "/usr/bin/pfexec"

ZONE_TMPL_SUFFIX = ".xml"
ZONE_TMPL_DIR = "/etc/zones"

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
    'incomplete' : 4, # during installation
}

# TODO: more Zone*Exceptions and replace Key/ValueErrors
class ZoneException(Exception):
    """General zone exception"""
    pass

class PrivilegesError(Exception):
    """
    Exception signalizing that user does not have required permissions
    """
    pass

def check_zone_template(template):
    """
    @raise ZoneException in case that template does not exist
    @param template
    """
    if not os.path.isfile(os.path.join(ZONE_TMPL_DIR, template +
        ZONE_TMPL_SUFFIX)):
        raise ZoneException("Template %s does not exist." % (template))

def check_user_permissions(profiles=("Primary Administrator",
                            ("Zone Management", "Zone Security"))):
    """
    this function is being used to check wheather the user is capable
    of executing zone* commands

    @param - profiles list of profiles to match. Default:
             ["Primary Administrator", ("Zone Management", "Zone Security")]

             user must be in all profiles listed per parent dict item
    @raise - PrivilegeError in case that none of profiles is being listed by
             profiles(1)
    """

    def sublist_in(lst, sublst):
        """
        simple check if items from sublst are part of list
        @param lst
        @param sublst
        """
        for i in sublst:
            if i not in lst:
                return False
        return True

    def oneof(item_list, items):
        """
        helper function if one of items is in item_list
        @param item_list
        @param items
        """
        for i in item_list:
            if type(i) == type(list()) or type(i) == type(dict()):
                if sublist_in(item_list, i):
                    return True
            else:
                if i in items: return True

        return False


    if os.uname()[0] == "SunOS" and profiles:
        profiles_output = getoutputs(["profiles", ], False)
        # line/output is something like \tPROFILE NAME\n
        # also we should remove last line as it's just \n
        prof_list = map(lambda a: a.strip(), profiles_output.split("\n"))[:-1]

        return oneof(prof_list, profiles)

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
        self._zone_attr = {}
        self.set_attr(ZONE_ENTRY['ZNAME'], name)

    def refresh_all_info(self):
        """
        Possibly all zone properties can be changed so let's refresh it asap
        """
        # Do not use uuid as it's not available in state configured
        # Do not use self.get_attr as it would call refresh_all_info again :-)
        state_cmd = [CMD_ZONEADM, "-z",
                self._zone_attr[ZONE_ENTRY['ZNAME']], "list",  "-p"]

        line_items = str(getoutputs(state_cmd)).split(":")
        for val in ZONE_ENTRY.values():
            # our ZONE_MAPING reflects _zone_attr
            self._zone_attr[val] = line_items[val]

    def set_attr(self, attr, value):
        """
        sets zone attribute
        @param attr - integer value from ZONE_ENTRY
        @param value - value

        Note: for now set_attr takes effect only on zone creation
        """
        if attr in ZONE_ENTRY.values():
            self._zone_attr[int(attr)] = value
        else:
            raise ZoneException("Unsupported ZONE_ENTRY attribute: %s." %
                            str(attr))

    def get_attr(self, attr, refresh=True):
        """
        returns zone attribute
        @param attr - integer value from ZONE_ENTRY
        @param refresh - wheather to refresh info from zoneadm list before
                         printing the value. Useful during zone creation.
                         or to avoid recursion for some reason.
        """

        if refresh:
            self.refresh_all_info() # runs zoneadm list

        # TODO thinking of try/except KeyError here
        return self._zone_attr[attr]

    #--------------------------------------------------------------------------
    # some extra set/add calls
    #--------------------------------------------------------------------------
    def remove_property(self, property_name, print_cmd=False):
        """
        removes property such as fs, dataset, net ...
        @param property_name - a string

        Note: RBAC (pfexec) aware
        """

        zonecfg_cmd = [CMD_PFEXEC, CMD_ZONECFG, "-z", self.get_name()]
        property_part = "remove %s; exit" % property_name
        zonecfg_cmd.append(property_part)

        if print_cmd:
            return [zonecfg_cmd, ]

        return getoutputs(zonecfg_cmd)

    def add_property(self, name, opts, print_cmd=False):
        """
        This function basically handles actions such as add fs ...
        @param name - e.g. capped-memory
        @param opts - dict with values {'attr1' : 'value1', }

        Note: RBAC (pfexec) aware
        """
        zonecfg_cmd = [CMD_PFEXEC, CMD_ZONECFG, "-z", self.get_name()]

        available_properties = {
            "capped-memory" : ("physical", "swap", "locked"),
            "capped-cpu" : ("ncpus",),
            "fs" : ("dir", "special", "type"),
            "dataset" : ("name",),
            # TODO "net" : (),
        }

        if name not in available_properties.keys():
            raise KeyError("Unsupported property '%s'. Supported properties are: %s." %
                name, available_properties[name])

        if set(opts.keys()) != set(available_properties[name]):
            raise ValueError("Given opts does not match requirements. Required opts: '%s'" %
                available_properties[name])

        prop_part = ["add %s" % name]

        for key, value in opts.iteritems():
            prop_part.append("set %s=%s" % (key, str(value)))

        prop_part.append("end") # End of section
        prop_part.append("exit")

        zonecfg_cmd.append(";".join(prop_part))
        if print_cmd:
            return [zonecfg_cmd, ]

        getoutputs(zonecfg_cmd)

    #--------------------------------------------------------------------------
    # wrapped get_attr calls
    #--------------------------------------------------------------------------
    def set_zonepath(self, path):
        """
        just wrapped set_attr as this will be used during zone creation
        @param path
        """
        self.set_attr(ZONE_ENTRY['ZROOT'], path)

    def get_zonepath(self, refresh=False):
        """
        returns an integer reprezenting state in ZONE_STATE
        @param refresh=True - refresh info from zoneadm list
        """
        return self.get_attr(ZONE_ENTRY['ZROOT'], refresh)

    def get_state(self, refresh=True):
        """
        returns an integer reprezenting state in ZONE_STATE
        please call refresh_all_info() before calling get_state()
        @param refresh=True - refresh info from zoneadm list
        """
        return ZONE_STATE[self.get_attr(ZONE_ENTRY['ZSTATE'], refresh)]

    def get_name(self, refresh=False):
        """
        returns zone name as listed by zoneadm list -pc
        @param refresh=False - refresh info from zoneadm list
        """
        return self.get_attr(ZONE_ENTRY['ZNAME'], refresh)

    def get_zone_root(self, refresh=False):
        """
        returns zone root
        eg. /zones/myzone/root
        @param refresh=False - refresh info from zoneadm list
        """
        return self.get_zonepath(refresh) + "/root"

    #--------------------------------------------------------------------------
    # Changing state of Zones
    #--------------------------------------------------------------------------

    def _zone_in_states(self, state_list):
        """
        @param state_list list of ZONE_STATE values
        @raise ZoneException in case that zone.get_state does not match
               any value in state_list
        """
        if self.get_state() not in state_list:
            raise ZoneException("Zone '%s' must be in one of states: %s."\
                    "Current state is %s." %
                    (self.get_name(), str(state_list), str(self.get_state())))

    def boot(self, print_cmd=False):
        """
        note: RBAC aware (pfexec and roles check)
        @print_cmd=False - don't execute anything only return a list with
                           commands [['pfexec' ,...], ]
        """
        check_user_permissions()

        self._zone_in_states((ZONE_STATE['installed'],))
        boot_cmd = [CMD_PFEXEC , CMD_ZONEADM, "-z", self.get_name(), "boot"]
        if print_cmd:
            return [boot_cmd, ]

        return getoutputs(boot_cmd)


    def ready(self):
        """
        note: RBAC aware (pfexec and roles check)
        """
        check_user_permissions()

        self._zone_in_states((ZONE_STATE['installed'],))
        ready_cmd = [CMD_PFEXEC, CMD_ZONEADM, "-z", self.get_name(), "ready"]
        return getoutputs(ready_cmd)

    def shutdown(self):
        """
        note: RBAC aware (pfexec and roles check)
        """
        check_user_permissions()

        self._zone_in_states((ZONE_STATE['running'],))
        shutdown_cmd = [CMD_PFEXEC , CMD_ZONEADM, "-z", self.get_name(),
                "shutdown"]
        return getoutputs(shutdown_cmd)

    def halt(self):
        """
        note: RBAC aware (pfexec and roles check)
        """
        check_user_permissions()

        self._zone_in_states((ZONE_STATE['running'],))
        halt_cmd = [CMD_PFEXEC , CMD_ZONEADM, "-z", self.get_name(), "halt"]
        return getoutputs(halt_cmd)

    def reboot(self):
        """
        note: RBAC aware (pfexec and roles check)
        """
        check_user_permissions()

        self._zone_in_states((ZONE_STATE['running'],))
        reboot_cmd = [CMD_PFEXEC , CMD_ZONEADM, "-z", self.get_name(),
                "shutdown", "-r"]
        return getoutputs(reboot_cmd)

    #--------------------------------------------------------------------------
    # Install / Clone
    #--------------------------------------------------------------------------
    def install(self, print_cmd=False):
        """
        note: RBAC aware (pfexec and roles check)
        @print_cmd=False - don't execute anything only return a list with
                           commands [['pfexec' ,...], ]
        """
        check_user_permissions()

        self._zone_in_states((ZONE_STATE['configured'],))

        install_cmd = [CMD_PFEXEC, CMD_ZONEADM, "-z", self.get_name(),
                "install"]

        if print_cmd:
            return [install_cmd, ]
        return getoutputs(install_cmd)
        # TODO post install configuration

    def clone(self, source_zone, print_cmd=False):
        """
        note: RBAC aware (pfexec and roles check)
        @source_zone - a Zone() object in a installed state
        @print_cmd=False - don't execute anything only return a list with
                           commands [['pfexec' ,...], ]
        """
        # raise exception if it's not halted
        source_zone._zone_in_states((ZONE_STATE['installed']))

        clone_cmd = [CMD_PFEXEC, CMD_ZONEADM, "-z", self.get_name(), "clone", source_zone.get_name()]
        if print_cmd:
            return [clone_cmd, ]
        return getoutputs(install_cmd)

    #--------------------------------------------------------------------------
    # Deletion / Creation
    #--------------------------------------------------------------------------
    def exists(self):
        """
        function returns True in case that zone already exist otherwise
        false is returned
        """
        return bool(get_zone_by_name(self.get_name(refresh=False)))

    def create(self, template, print_cmd=False):
        """
        creates a zone from given configuration
        @param template - one of /etc/zones/*.xml without suffix
        @print_cmd=False - don't execute anything only return a list with
                           commands [['pfexec' ,...], ]
        """
        return self._create_minimal(template, print_cmd)

        #self._write_sysidcfg()

    def _create_minimal(self, template, print_cmd=False):
        """
        minimal form of the creation command
        Note: RBAC aware (pfexec and roles check)
        @param template - one of /etc/zones/*.xml without suffix
        """
        check_user_permissions()
        if self.exists(): raise ZoneException("Zone already exists.")

        check_zone_template(template)


        cmd_base = ["pfexec", CMD_ZONECFG, "-z", self.get_name(refresh=False)]
        minimal_config = ["create -t %s" % template,
                "set zonepath=%s" % self.get_zonepath(refresh=False), "exit"]
        cmd_base.append(";".join(minimal_config))

        if print_cmd:
            return [cmd_base, ]
        return getoutputs(cmd_base)



    def _write_sysidcfg(self, config_dict):
        """
        post install configuration of the zone
        this should be called only by self.create()

        """
        sysidcfg_path = os.path.join(self.get_zone_root(), "etc",
                "sysidcfg")

        cfg_file = None

        defaults = {
            "root_password"      : "test",
            "systen_locale"      : "en_US",
            "timeserver"         : "localhost",
            "timezone"           : "US/Eastern",
            "terminal"           : "vt100",
            "security_policy"    : "NONE",
            "nfs4_domain"        : "localdomain",
            "name_service"       : "NONE",
            #these values require name_service : DNS {\ndomain_name=val\n...}
            "domain_name"        : None,
            "name_server"        : None, # A IPs separated by comma
            "search"             : None, # Hosts separated by comma
            # oev

            # need to check if this is necessary when there is no networking
            "network_interface"  : "PRIMARY",
            "ip_address"         : "127.0.0.1",
            "netmask"            : "255.255.255.0",
            "protocol _ipv6"     : "no",
            "default_route"      : "127.0.0.1",


        }

        # This is probably the only reason why Zone Admin is not enough
#        cfg_file = open(sysidcfg_path, "w")

        # Contents shoudld vary according to network settings
        # let's leave this simple since we don't support networking yet

    def _zonecfg_set(self, attr, value):
        """
        note: RBAC aware (pfexec and roles check)
        @param attr - attribute a string e.g. zonepath
        @param value - value
        """
        check_user_permissions()
        cmd_base = [CMD_PFEXEC, CMD_ZONECFG, "-z", self.get_name()]
        cmd_base.append("set %s=%s;exit" % (str(attr), str(value)))
        return getoutputs(cmd_base)

    def uninstall(self):
        check_user_permissions()
        self._zone_in_states((ZONE_STATE['installed'],
         ZONE_STATE['incomplete']))
        uninstall_cmd = [CMD_PFEXEC, CMD_ZONEADM, "-z", self.get_name(),
         "uninstall", "-F"]
        return getoutputs(uninstall_cmd)

    def delete(self):
        """
        Note: RBAC aware (pfexec and roles check)
        """
        check_user_permissions()
        self._zone_in_states((ZONE_STATE['configured'], ZONE_STATE['incomplete']))
        del_cmd = [CMD_PFEXEC, CMD_ZONECFG, "-z", self.get_name(), "delete",
         "-F"]
        return getoutputs(del_cmd)

    #--------------------------------------------------------------------------
    # Remote execution
    #--------------------------------------------------------------------------

    def execute(self, cmd, user="root", print_cmd=False):
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

        self._zone_in_states((ZONE_STATE['running'],))
        #zlogin [ -dCES ] [ -e cmdchar ] [-l user] zonename [command [args ...]]
        zlogin_cmd = [CMD_PFEXEC, CMD_ZLOGIN]

        if user:
            zlogin_cmd.append("-l")
            zlogin_cmd.append("%s" % user)

        zlogin_cmd.append(self.get_name())
        zlogin_cmd.append("%s" % str(cmd))

        if print_cmd:
            return [zlogin_cmd, ]
        return getoutputs(zlogin_cmd)

# End of Class

def get_zone_by_name(zname):
    """
    returns Zone() instance
    """
    for zone in list_zones():
        if zone.get_name() == zname:
            return zone

    return None

def list_zone_names():
    """
    returns list of Zone(*).get_name() outputs
    """
    get_name = lambda a: a.get_name()
    return map(get_name, list_zones())

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
        zone.set_attr(attr, line[attr])

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
