#!/usr/bin/env python3

# Copyright (c) 2019 Jens Georg
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import binascii
import datetime as dt
import struct
import bitstring
import hashlib

import sqlobject

import serial

sqlobject.sqlhub.processConnection = sqlobject.connectionForURI('sqlite:data.sqlite')

import matplotlib.pyplot as plt


class CycleParser:
    HEADER_START=3
    FIRST_RECORD=33
    RECORD_LENGTH=32

    def __init__(self, data):
        self.raw_data = data
        self.measurements = list()
        b = data[CycleParser.HEADER_START:CycleParser.FIRST_RECORD]
        self.data = binascii.unhexlify(bytearray(b))
        [self.number_of_cycles, self.user] = struct.unpack('B2x12s', self.data)

        # The 12 bytes of user ID are padded with 0x99, skip all the padding
        self.user = self.user.decode(errors='ignore')

        print ("Number of cycles found in data {}".format(self.number_of_cycles))
        print ("User: {}".format(self.user))

        for offset in self.cycles():
            record = bytearray(self.raw_data[offset:offset+CycleParser.RECORD_LENGTH + 1])
            try:
                self.measurements.append(Measurement(self.user, record))
            except sqlobject.dberrors.DuplicateEntryError:
                pass

    def cycles(self):
        for record in range(0, self.number_of_cycles):
            yield CycleParser.FIRST_RECORD + record * CycleParser.RECORD_LENGTH


class Measurement(sqlobject.SQLObject):
    hash = sqlobject.col.StringCol(unique=True)
    datetime = sqlobject.col.DateTimeCol()
    sys = sqlobject.col.IntCol()
    dia = sqlobject.col.IntCol()
    pulse = sqlobject.col.IntCol()
    pp = sqlobject.col.IntCol()
    map = sqlobject.col.IntCol()

    def __init__(self, user, record):
        md5 = hashlib.md5()
        md5.update(user.encode())
        md5.update(record)

        _hash = md5.hexdigest()

        try:
            _datetime = dt.datetime.strptime(record[0:10].decode(), '%y%m%d%H%M')
        except ValueError:
            _datetime = dt.datetime(2015,1,1)

        pressure_data = binascii.unhexlify(record[16:24])

        # blood pressure data is in 30 bits
        bs = bitstring.ConstBitStream(bytes=pressure_data)
        bs.pos += 2
        _pulse, _dia, _sys = bs.readlist(['uint:10, uint:10, uint:10'])

        _pp = _sys - _dia
        _map = _dia + _pp / 3
        super().__init__(hash=_hash, datetime=_datetime, sys=_sys, dia=_dia, pulse=_pulse, pp=_pp, map=_map)


if __name__ == '__main__':
    Measurement.createTable(ifNotExists=True)

    with serial.Serial('/dev/ttyUSB0', 19200, timeout=1) as ser:
        ser.write(bytearray([0x12, 0x16, 0x18, 0x22]))
        data = bytearray()
        while True:
            buf = ser.read(32)
            data.extend(buf)
            if len(buf) < 32:
                break;

        p = CycleParser(data)
        d = Measurement.select()
