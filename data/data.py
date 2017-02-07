#!/usr/bin/env python
"""
D8.py
Static (mysql) log viewer for the L8 redis-backed logger.

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

import datetime
import json
import math
import redis
import sys
import time
import re
import base64
import argparse
from bcolors import bcolors
import pymysql as mysql
import pymysql.err as mysql_exceptions

mysql.install_as_MySQLdb()

class Data:
    def __init__(self, args):
        self.start_time = time.time() - (7 * 24 * 60 * 60)
        self.end_time = time.time() + (24 * 60 * 60)
        self.error_levels = {
            self.levels.DEBUG: args.eDEBUG,
            self.levels.INFO: args.eINFO,
            self.levels.NOTICE: args.eNOTICE,
            self.levels.WARNING: args.eWARNING,
            self.levels.ERROR: args.eERROR,
            self.levels.CRITICAL: args.eCRITICAL,
            self.levels.ALERT: args.eALERT,
            self.levels.EMERGENCY: args.eEMERGENCY,
        }
        try:
            self.mysql = mysql.connect(args.host, args.username, args.password, args.database)
        except (mysql_exceptions.OperationalError, mysql_exceptions.ProgrammingError) as err:
            raise ConnectionError(err)

    def __del__(self):
        self.mysql.close()

    @staticmethod
    def format_timestamp(ts):
        return time.strftime('%Y-%m-%d', time.gmtime(ts))

    @staticmethod
    def format_datetime(ts):
        return ts.strftime("%Y-%m-%d")

    def get_time_sql(self):
        return 'DATE(time) >= "{0}" AND DATE(time) <= "{1}"'.format(self.format_timestamp(self.start_time), self.format_timestamp(self.end_time))

    def get_level_sql(self):
        return 'level IN ("{0}")'.format('","'.join([self.levels.keys[i] for i in self.error_levels if self.error_levels[i]]))

    def get_counts_sql(self):
        return ', '.join(["SUM(`level` = '%s')" % self.levels.keys[i] for i in self.error_levels if self.error_levels[i]])

    def domains(self):
        with self.mysql.cursor() as cursor:
            sql = 'SELECT domain, count(*), {2} as count FROM `messages` WHERE {0} AND {1} GROUP BY domain ORDER BY count DESC'.format(
                self.get_time_sql(),
                self.get_level_sql(),
                self.get_counts_sql()
            )
            cursor.execute(sql)
            res = []
            while True:
                record = cursor.fetchone()
                if not record:
                    break

                counts = {self.levels.keys[i]: int(record[i + 2]) for i in self.error_levels if self.error_levels[i]}
                res.append(self.Domain(record[0], record[1], **counts))
            return res

    def errors(self, host, mode):
        with self.mysql.cursor() as cursor:
            if mode == self.mode.totals:
                cursor.execute('SELECT filename, line, message, level, source, context, count(*) as count, unix_timestamp(MAX(time)), id, domain FROM `messages` WHERE domain = "{0}" AND {1} AND {2} GROUP BY filename, line ORDER BY count DESC'.format(
                    host,
                    self.get_time_sql(),
                    self.get_level_sql())
                )
            else:
                cursor.execute('SELECT filename, line, message, level, source, context, 1 as count, unix_timestamp(time), id, domain FROM `messages` WHERE domain = "{0}" AND {1} AND {2} ORDER BY time DESC'.format(
                    host,
                    self.get_time_sql(),
                    self.get_level_sql())
                )
            res = []
            while True:
                record = cursor.fetchone()
                if not record:
                    break
                res.append(self.Error(record[8], record[0], record[1], record[2], record[3], record[4], record[5], record[6], record[7], record[9]))
            return res

    def get_error(self, id):
        with self.mysql.cursor() as cursor:
            cursor.execute('SELECT filename, line, message, level, source, context, 1 as count, time, id, domain FROM `messages` WHERE id = %s' % id)
            record = cursor.fetchone()
            if not record:
                raise LookupError("Error record not found")

            return self.Error(record[8], record[0], record[1], record[2], record[3], record[4], record[5], record[6], record[7], record[9])
            
    def delete_type(self, error):
        with self.mysql.cursor() as cursor:
            sql = "DELETE FROM messages WHERE line = %s AND filename = %s AND domain = %s"
            parameters = (
                error.line,
                error.file,
                error.domain
            )
            cursor.execute(sql, parameters)
            self.mysql.commit()

    def delete_entry(self, error):
        with self.mysql.cursor() as cursor:
            cursor.execute("DELETE FROM messages WHERE id = %s", error.id)
            self.mysql.commit()

    @staticmethod
    def invalid_connection(err, args):
        sys.stdout.write('%s%s%s%s\n' % (bcolors.FAIL, bcolors.UNDERLINE, "MYSQL error: ", bcolors.ENDC))
        sys.stdout.write('%s%s%s\n' % (bcolors.FAIL, err, bcolors.ENDC))
        sys.stdout.write('%sCREATE DATABASE %s;%s\n' % (bcolors.WARNING, args.database, bcolors.ENDC))
        sys.stdout.write('%s\
CREATE TABLE `messages` (\n\
  `id` int(11) NOT NULL AUTO_INCREMENT,\n\
  `domain` varchar(255) DEFAULT NULL,\n\
  `time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,\n\
  `level` enum("DEBUG","INFO","NOTICE","WARNING","ERROR","CRITICAL","ALERT","EMERGENCY") DEFAULT NULL,\n\
  `source` enum("STATEMENT","ERROR","EXCEPTION") DEFAULT NULL,\n\
  `message` text,\n\
  `filename` varchar(255) DEFAULT NULL,\n\
  `line` int(10) DEFAULT NULL,\n\
  `context` text\n\
) ENGINE=InnoDB DEFAULT CHARSET=utf8;%s\n' % (bcolors.WARNING, bcolors.ENDC))
        sys.stdout.write('%sCREATE USER "%s"@"%s" IDENTIFIED BY "%s";%s\n' % (
            bcolors.WARNING, args.username, args.host, args.password, bcolors.ENDC))
        sys.stdout.write('%sGRANT ALL PRIVILEGES ON `%s`.* TO "%s"@"%s";%s\n' % (
            bcolors.WARNING, args.database, args.username, args.host, bcolors.ENDC))
        sys.stdout.write('%sFLUSH PRIVILEGES;;%s\n' % (bcolors.WARNING, bcolors.ENDC))

    """
    Context 1.0.0 format:

        {
            version:  <string> - context version
            id:       <long>   - unique message identifier
            domain:   <string> - domain name of generated event (may be None)
            time:     <int>    - unix timestamp (utc) of event
            level:    <int>    - severity (1=DEBUG, 2=INFO, 4=NOTICE,
                                           8=WARNING, 16=ERROR, 32=CRITICAL,
                                           64=ALERT, 128=EMERGENCY)
            source:   <int>    - source of event (1=statement, 2=error,
                                                  3=exception)
            message:  <string> - the message itself (utf-8)
            filename: <string> - originating filename
            line:     <int>    - originating line number
            context:  <array>  - json encoded context
        }
    """

    def add_entry(self, record):
        try:
            with self.mysql.cursor() as cursor:
                sql = "INSERT into messages ( `domain` ,  `time` ,  `level` ,  `source` , `message` , `filename` , `line` , `context` ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
                parameters = (
                    record['domain'],
                    time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(record['time'])),
                    math.log(record['level'], 2) + 1, record['source'],
                    record['message'],
                    record['filename'],
                    record['line'],
                    record['context']
                )
                cursor.execute(sql, parameters)
                self.mysql.commit()
        except (mysql.ProgrammingError, mysql.OperationalError) as err:
            if err.args[0] == 2006:
                self.connect()
                self.work(item)
            else:
                sys.stdout.write('%sMYSQL error: %s%s\n' % (bcolors.FAIL, err, bcolors.ENDC))
            pass
        except TypeError as err:
            sys.stdout.write("%sFormat Error:%s%s\n" % (bcolors.FAIL, err, bcolors.ENDC))
            pass

    class mode:
        totals = 1
        latest = 2

    class Domain:
        def __init__(self, host, error_count, **kwargs):
            self.host = host
            self.error_count = error_count
            self.counts = kwargs

    class Error:
        def __init__(self, id, file, line, message, level, source, context, count, time, domain):
            self.id = id
            self.time = time
            self.count = count
            try:
                self.context = json.loads(base64.b64decode(context))
            except (TypeError, ValueError) as e:
                try:
                    self.context = json.loads(context)
                except (TypeError, ValueError) as e2:
                    self.context = str(e2) + " : " + context
            self.source = source
            self.level = level
            self.message = message
            self.line = line
            self.file = file
            self.domain = domain

    class levels:
        keys = ['DEBUG', 'INFO', 'NOTICE', 'WARNING', 'ERROR', 'CRITICAL', 'ALERT', 'EMERGENCY']
        DEBUG = 0
        INFO = 1
        NOTICE = 2
        WARNING = 3
        ERROR = 4
        CRITICAL = 5
        ALERT = 6
        EMERGENCY = 7

class ConnectionError(Exception):
    pass
