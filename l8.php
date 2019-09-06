<?php

/**
 * L8.php
 * High-speed, zero-dependancy RFC-5424 compatable redis-backed logger for PHP.
 *
 * Copyright (C) 2014 Alan McFarlane <alan@node86.com>
 * All Rights Reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * 1. Redistributions of source code must retain the above copyright notice,
 *    this list of conditions and the following disclaimer.
 *
 * 2. Redistributions in binary form must reproduce the above copyright notice,
 *    this list of conditions and the following disclaimer in the documentation
 *    and/or other materials provided with the distribution.
 *
 * 3. Neither the name of the copyright holder nor the names of its
 *    contributors may be used to endorse or promote products derived from this
 *    software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
 * ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
 * LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
 * CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 * SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
 * CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 **/
class L8 {
    // context version
    const VERSION = '1.1.0';

    // redis configuration
    public static $server = 'localhost:6379';
    public static $db = 1;
    public static $channel = 'L8';      // NB will also use <$channel>_seq

    // syslog facilities
    const DEBUG     = 1;
    const INFO      = 2;
    const NOTICE    = 4;
    const WARNING   = 8;
    const ERROR     = 16;
    const CRITICAL  = 32;
    const ALERT     = 64;
    const EMERGENCY = 128;

    // data source
    const LOG_STATEMENT     = 1;
    const ERROR_HANDLER     = 2;
    const EXCEPTION_HANDLER = 3;

    // internals
    protected static $socket;
    protected static $domain;

    /* -- */

    public static function debug($message, array $context = array()) {
        return static::log(static::DEBUG, $message, $context);
    }

    public static function info($message, array $context = array()) {
        return static::log(static::INFO, $message, $context);
    }

    public static function notice($message, array $context = array()) {
        return static::log(static::NOTICE, $message, $context);
    }

    public static function warning($message, array $context = array()) {
        return static::log(static::WARNING, $message, $context);
    }

    public static function error($message, array $context = array()) {
        return static::log(static::ERROR, $message, $context);
    }

    public static function critical($message, array $context = array()) {
        return static::log(static::CRITICAL, $message, $context);
    }

    public static function alert($message, array $context = array()) {
        return static::log(static::ALERT, $message, $context);
    }

    public static function emergency($message, array $context = array()) {
        return static::log(static::EMERGENCY, $message, $context);
    }

    /* -- */

    protected static function log($level, $message, array $context = array()) {
        if (count($trace = debug_backtrace(false, 2)) > 1) {
            $file = $trace[1]['file'];
            $line = $trace[1]['line'];
        } else {
            $file = '';
            $line = 0;
        }

        return static::write($level, static::LOG_STATEMENT, $message, $file,
            $line, $context);
    }

    /* -- */

    public static function set_error_handler() {
        set_error_handler([get_called_class(), 'error_handler']);
    }

    public static function error_handler($errno, $message, $file = '', $line = 0,
                                         $context = array()) {
        if (!is_array($context)) {
            $context = array($context);
        }

        $map = array(
            E_ERROR => array('E_ERROR', static::ERROR),
            E_WARNING => array('E_WARNING', static::WARNING),
            E_PARSE => array('E_PARSE', static::ERROR),
            E_NOTICE => array('E_NOTICE', static::NOTICE),
            E_CORE_ERROR => array('E_CORE_ERROR', static::ERROR),
            E_CORE_WARNING => array('E_CORE_WARNING', static::WARNING),
            E_COMPILE_ERROR => array('E_COMPILE_ERROR', static::ERROR),
            E_COMPILE_WARNING => array('E_COMPILE_WARNING', static::WARNING),
            E_USER_ERROR => array('E_USER_ERROR', static::ERROR),
            E_USER_WARNING => array('E_USER_WARNING', static::WARNING),
            E_USER_NOTICE => array('E_USER_NOTICE', static::NOTICE),
            E_STRICT => array('E_STRICT', static::WARNING),
            E_RECOVERABLE_ERROR => array('E_RECOVERABLE_ERROR', static::WARNING),
            E_DEPRECATED => array('E_DEPRECATED', static::WARNING),
            E_USER_DEPRECATED => array('E_USER_DEPRECATED', static::WARNING),
        );

        list($prefix, $level) = array_key_exists($errno, $map)
            ? $map[$errno]
            : array('E_UNKOWN(' . $errno . ')', static::ERROR);

        return static::write($level, static::ERROR_HANDLER, $prefix . ':' .
            $message, $file, $line, $context);
    }

    public static function exception_handler($e) {
        return static::write(static::ERROR, static::EXCEPTION_HANDLER,
            $e->getMessage(),
            $e->getFile(), $e->getLine(), array());
    }

    /* -- */

    protected static function write($level, $source, $message, $file, $line,
                                  $context) {
        // connect to redis server
        if (!isset(static::$socket)) {
            static::$socket = stream_socket_client(static::$server);
            if (static::$socket) {
                static::select(static::$db);

                static::$domain = array_key_exists('SERVER_NAME', $_SERVER)
                    ? strtolower($_SERVER['SERVER_NAME'])
                    : null;
            }
        }

        // make sure the socket was opened
        if (!static::$socket) {
            return false;
        }

        // generate the atomic log entry id #
        $id = static::incr(self::$channel . '.seq');
        if ($id == '9223372036854775807') {                 // 2^63-1
            $redis->set(self::$channel . '.seq', 0);
        }

        // construct the data record
        $record = json_encode(
            array(
                'version' => static::VERSION,
                'id' => $id,
                'domain' => static::$domain,
                'time' => time(),
                'level' => $level,
                'source' => $source,
                'message' => $message,
                'filename' => $file,
                'line' => $line,
                'context' => base64_encode(json_encode($context)),
            )
        );

        static::publish(self::$channel, $record);

        return true;
    }

    /* -- */

    protected static function incr($key) {
        return static::execute(array('INCR', $key));
    }

    protected static function publish($channel, $message) {
        return static::execute(array('PUBLISH', $channel, $message));
    }

    protected static function select($index) {
        return static::execute(array('SELECT', $index));
    }

    protected static function set($key, $value) {
        return static::execute(array('SET', $key, $value));
    }

    /* -- */

    protected static function execute($args) {
        $cmd = '*' . count($args) . "\r\n";
        foreach ($args as $arg) {
            $cmd .= '$' . strlen($arg) . "\r\n" . $arg . "\r\n";
        }

        fwrite(static::$socket, $cmd);

        return static::parseResponse();
    }

    protected static function parseResponse() {
        $line = fgets(static::$socket);

        list($type, $result) = array(
            $line[0],
            substr($line, 1,
                strlen($line) - 3)
        );

        if ($type == '-') {
            throw new Exception($result);
        } elseif ($type == '$') {
            if ($result == -1) {
                $result = null;
            } else {
                $line = fread(static::$socket, $result + 2);
                $result = substr($line, 0, strlen($line) - 2);
            }
        } elseif ($type == '*') {
            $count = (int)$result;

            for ($i = 0, $result = array(); $i < $count; $i++) {
                $result[] = static::parseResponse();
            }
        }

        return $result;
    }
}
