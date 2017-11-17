# Copyright (c) 2015 Yubico AB
# All rights reserved.
#
#   Redistribution and use in source and binary forms, with or
#   without modification, are permitted provided that the following
#   conditions are met:
#
#    1. Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#    2. Redistributions in binary form must reproduce the above
#       copyright notice, this list of conditions and the following
#       disclaimer in the documentation and/or other materials provided
#       with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from .util import PID, TRANSPORT, Mode
from .device import YubiKey
from .driver_ccid import open_devices as open_ccid
from .driver_u2f import open_devices as open_u2f
from .driver_otp import open_devices as open_otp
from .native.pyusb import get_usb_backend

import usb.core
import time


class FailedOpeningDeviceException(Exception):
    pass


class Descriptor(object):

    def __init__(self, pid, version, serial=None):
        self._version = version
        self._pid = pid
        self._serial = serial
        self._key_type = pid.get_type()
        self._mode = Mode.from_pid(pid)

    @property
    def version(self):
        return self._version

    @property
    def pid(self):
        return self._pid

    @property
    def mode(self):
        return self._mode

    @property
    def key_type(self):
        return self._key_type

    def open_device(self, transports=sum(TRANSPORT), attempts=3):
        transports &= self.mode.transports
        driver = open_driver(transports, self._serial, self._pid, attempts)
        if self._serial is None:
            self._serial = driver.serial
        return YubiKey(self, driver)

    @classmethod
    def from_usb(cls, usb_dev):
        v_int = usb_dev.bcdDevice
        version = ((v_int >> 8) % 16, (v_int >> 4) % 16, v_int % 16)
        pid = PID(usb_dev.idProduct)
        return cls(pid, version)

    @classmethod
    def from_driver(cls, driver):
        return cls(driver.pid, driver.guess_version(), driver.serial)


def _gen_descriptors():
    found = []  # Composite devices are listed multiple times on Windows...
    for dev in usb.core.find(True, idVendor=0x1050, backend=get_usb_backend()):
        try:
            addr = (dev.bus, dev.address)
            if addr not in found:
                found.append(addr)
                yield Descriptor.from_usb(dev)
        except ValueError:
            pass  # Invalid PID.


def get_descriptors():
    return list(_gen_descriptors())


def list_drivers(transports=sum(TRANSPORT)):
    if TRANSPORT.CCID & transports:
        for dev in open_ccid():
            if dev:
                yield dev
    if TRANSPORT.OTP & transports:
        for dev in open_otp():
            if dev:
                yield dev
    if TRANSPORT.U2F & transports:
        for dev in open_u2f():
            if dev:
                yield dev


def open_driver(transports=sum(TRANSPORT), serial=None, pid=None, attempts=3):
    for attempt in range(attempts):
        sleep_time = (attempt + 1) * 0.1
        for drv in list_drivers(transports):
            if drv is not None:
                if serial is not None and drv.serial != serial:
                    del drv
                    continue
                if pid is not None and drv.pid != pid:
                    del drv
                    continue
                return drv
        #  Wait a little before trying again.
        time.sleep(sleep_time)
    raise FailedOpeningDeviceException()


def open_device(transports=sum(TRANSPORT), serial=None, pid=None, attempts=3):
    driver = open_driver(transports, serial, pid, attempts)
    matches = [d for d in get_descriptors() if d.pid == driver.pid]
    if len(matches) > 0:  # Use the descriptor with the lowest version
        matches.sort(key=lambda d: d.version)
        descriptor = matches[0]
    else:
        descriptor = Descriptor.from_driver(driver)
    return YubiKey(descriptor, driver)
