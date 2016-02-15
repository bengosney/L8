#!/usr/bin/env python
"""
A8.py
Context based alert tool based of errors logged by S8

Copyright (C) 2014-2015 Alan McFarlane <alan@node86.com>
Copyright (C) 2014-2015 Rob Chett <robchett@gmail.com>
All Rights Reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from this
   software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.
"""

import ConfigParser
from data.data import Data
from data.subscriber import Subscriber
from data.bcolors import bcolors
from pushbullet import Pushbullet

# Ignore warnings for depricated ssl version
import urllib3

urllib3.disable_warnings()


class Processor:
    def __init__(self, data):
        self.data = data
        self.config = Config()
        self.domains = {}

    def work(self, data):
        host = data['domain']
        if not host in self.domains:
            self.domains[host] = Domain(host, self.config.get_host(host))
        self.domains[host].add_error(data)


class Domain:
    def __init__(self, host, config):
        self.host = host
        self.config = config
        self.error_level = 0
        self.push_bullet = None
        pass

    def add_error(self, data):
        self.error_level += self.config['weighting_{}'.format(self.reverse_level(data['level']))]
        if self.error_level > self.config['tolerance']:
            self.alert('')
            self.error_level = 0
        else:
            print "%s: remaining tolerance - %d" % (self.host, self.config['tolerance'] - self.error_level)

    def alert(self, message):
        channels = self.config['channel']
        for channel in channels:
            if channel[:5] == 'push:':
                self.alert_push_notification(message, channel)
            else:
                self.alert_push_notification(message, channel)

    def alert_push_notification(self, message, channel):
        if self.push_bullet is None:
            self.push_bullet = Pushbullet(channel[5:])
        push = self.push_bullet.push_note("%s: tolerance of %d exceeded" % (self.host, self.config['tolerance']), message)
        print push

    def alert_email(self, message, channel):
        pass

    def reverse_level(self, level):
        return {
            '1': 'debug',
            '2': 'info',
            '4': 'notice',
            '8': 'warning',
            '16': 'error',
            '32': 'critical',
            '64': 'alert',
            '128': 'emergency',
        }["%d" % level]


class Config(ConfigParser.ConfigParser):
    def __init__(self):
        import os.path

        ConfigParser.ConfigParser.__init__(self, {
            'tolerance': 1000,
            'channel': [
                'push:DyhiIFDRz6Rb3j4RiqnadVdqxNhXZ7i6'
            ],
            'weighting_DEBUG': 0,
            'weighting_INFO': 0,
            'weighting_NOTICE': 5,
            'weighting_WARNING': 15,
            'weighting_ERROR': 50,
            'weighting_CRITICAL': 100,
            'weighting_ALERT': 500,
            'weighting_EMERGENCY': 1000,
        })

        conf_path = os.path.expanduser('~') + '/.a8'

        if os.path.isfile(conf_path):
            self.read(conf_path)
        else:
            self.add_section('base')

    def check_section(self, section):
        if not self.has_section(section):
            self.add_section(section)

    def get_host(self, section):
        if not self.has_section(section):
            self.add_section(section)
        return dict(self.items(section, True))


if __name__ == "__main__":
    from data.config import args as db_args

    bcolors.print_colour("A8: alerting tool\n", bcolors.OKGREEN, bcolors.UNDERLINE)
    bcolors.print_colour("Press Ctrl-C to exit\n", bcolors.OKGREEN, )

    try:
        data = Data(db_args)
        p = Processor(data)
        s = Subscriber()
        s.work(p.work)
    except (KeyboardInterrupt, SystemExit):
        pass