from django.db import models
from django.utils import timezone
from datetime import datetime
import plistlib
from xml.parsers.expat import ExpatError
import base64
import bz2
from uuid import uuid4
from django.contrib.auth.models import User, Group

class BusinessUnit(models.Model):
    hash = models.CharField(max_length=36, default=uuid4, primary_key=True, unique=True)
    name = models.CharField(max_length=30, unique=True)
    
    class Meta:
        permissions = (("can_view_businessunit", "Can view business unit"),)   

    def machines(self):
        return Machine.objects.filter(businessunit=self).count()

class Machine(models.Model):
    serial_number = models.CharField(max_length=16, unique=True, primary_key=True)
    hostname = models.CharField(max_length=64)
    username = models.CharField(max_length=256)
    location = models.CharField(max_length=256)
    remote_ip = models.CharField(max_length=15)
    businessunit = models.ForeignKey(BusinessUnit, null=True, blank=True, default=None)
    machine_model = models.CharField(
        max_length=64, blank=True, default="virtual-machine")
    cpu_type = models.CharField(max_length=64, blank=True)
    cpu_speed = models.CharField(max_length=32, blank=True)
    cpu_arch = models.CharField(max_length=32, blank=True)
    ram = models.CharField(max_length=16)
    os_version = models.CharField(max_length=16)
    available_disk_space = models.IntegerField(default=0)
    mac = models.CharField(max_length=17)
    last_munki_update = models.DateTimeField(default=datetime(1, 1, 1, 0, 0))
    last_inventory_update = models.DateTimeField(
        default=datetime(1, 1, 1, 0, 0))
    class Meta:
        ordering = ['hostname']

class MunkiReport(models.Model):
    machine = models.ForeignKey(Machine)
    timestamp = models.DateTimeField(default=timezone.now)
    runtype = models.CharField(max_length=64)
    runstate = models.CharField(max_length=16)
    console_user = models.CharField(max_length=64)
    errors = models.IntegerField(default=0)
    warnings = models.IntegerField(default=0)
    activity = models.TextField(editable=False, null=True)
    report = models.TextField(editable=False, null=True)
    class Meta:
        ordering = ['machine']
        permissions = (("can_view_reports", "Can view reports"),
                       ("can_view_dashboard", "Can view dashboard"),)
        
    def hostname(self):
        return self.machine.hostname
        
    def mac(self):
        return self.machine.mac
    
    def encode(self, plist):
        string = plistlib.writePlistToString(plist)
        bz2data = bz2.compress(string)
        b64data = base64.b64encode(bz2data)
        return b64data
        
    def decode(self, data):
        # this has some sucky workarounds for odd handling
        # of UTF-8 data in sqlite3
        try:
            plist = plistlib.readPlistFromString(data)
            return plist
        except:
            try:
                plist = plistlib.readPlistFromString(data.encode('UTF-8'))
                return plist
            except:
                try:
                    return self.b64bz_decode(data)
                except:
                    return dict()
        
    def b64bz_decode(self, data):
        try:
            bz2data = base64.b64decode(data)
            string = bz2.decompress(bz2data)
            plist = plistlib.readPlistFromString(string)
            return plist
        except Exception:
            return {}
        
    def get_report(self):
        return self.decode(self.report)
        
    def get_activity(self):
        return self.decode(self.activity)
        
    def update_report(self, base64bz2report):
        # Save report.
        try:
            base64bz2report = base64bz2report.replace(" ", "+")
            plist = self.b64bz_decode(base64bz2report)
            #self.report = base64bz2report
            self.report = plistlib.writePlistToString(plist)
        except:
            plist = None
            self.report = ''

        if plist is None:
            self.activity = None
            self.errors = 0
            self.warnings = 0
            self.console_user = "<None>"
            return
        
        # Check activity.
        activity = dict()
        for section in ("ItemsToInstall",
                        "InstallResults",
                        "ItemsToRemove",
                        "RemovalResults",
                        "AppleUpdates"):
            if (section in plist) and len(plist[section]):
                activity[section] = plist[section]
        if activity:
            #self.activity = self.encode(activity)
            self.activity = plistlib.writePlistToString(activity)
        else:
            self.activity = None
        
        # Check errors and warnings.
        if "Errors" in plist:
            self.errors = len(plist["Errors"])
        else:
            self.errors = 0
        
        if "Warnings" in plist:
            self.warnings = len(plist["Warnings"])
        else:
            self.warnings = 0
        
        # Check console user.
        self.console_user = "unknown"
        if "ConsoleUser" in plist:
            self.console_user = unicode(plist["ConsoleUser"])
