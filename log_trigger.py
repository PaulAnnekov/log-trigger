#!/usr/bin/env python3
import sys, json, signal, logging, smtplib, configparser, re, fnmatch, time, os, asyncio, socket
from email.mime.text import MIMEText

ansi_escape = re.compile(r'(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]')
# https://stackoverflow.com/questions/2595119/python-glob-and-bracket-characters
# ignore = {'home_assistant': ["*[[]roomba.roomba.Roomba[]]*\"error\":0,*",
#                                         "*[[]homeassistant.helpers.entity[]] Update of * is taking over 10 seconds",
#                                         "*[[]homeassistant.components.http[]] Serving /api/error/all to*",
#                                         "*[[]homeassistant.components.emulated_hue[]] When targeting Google Home, listening port has to be port 80",
#                                         "*[[]homeassistant.components.recorder[]] Ended unfinished session (*)",
#                                         "*[[]homeassistant.components.updater[]] Running on 'dev', only analytics will be submitted",
#                                         # Ignore system_log_event event and mqtt service which sends this event to mqtt server
#                                         "*[[]homeassistant.core[]] Bus:Handling <Event *system_log_event*",
#                                         # Z-wave component has service names and data with trigger words, filter them
#                                         "*INFO*[[]homeassistant.core[]]*service_registered*replace_failed_node*",
#                                         "*INFO*[[]homeassistant.core[]]*service_registered*remove_failed_node*",
#                                         "*INFO*[[]homeassistant.core[]]*state_changed*zwave.*is_failed*",
#                                         # If robot stuck, "error" field with description will be added
#                                         "*INFO*[[]homeassistant.core[]]*state_changed*vacuum.roomba*error*",
#                                         # Happens on clean cycle end, it's ok to ignore, it will reconnect
#                                         "*WARNING*[[]roomba.roomba.Roomba[]] Unexpected Disconnect From Roomba ! - reconnecting",
#                                         # http auth gives this warning if you don't use password
# 					"*WARNING*[[]homeassistant.components.http[]] You have been advised to set http.api_password.",
#     					# HA complains about custom components
#   					"*WARNING*[[]homeassistant.loader[]] You are using a custom integration for * which has not been tested by Home Assistant. This component might cause stability problems, be sure to disable it if you do experience issues with Home Assistant.",
#                                         # Bug https://github.com/home-assistant/home-assistant/issues/17408
#                                         "*WARNING*[[]homeassistant.components.binary_sensor.xiaomi_aqara[]] Unsupported movement_type detected: None",
#                                         # Called by UI when you open https://smart.home.annekov.com/dev-info page
#                                         "*INFO*[[]homeassistant.components.http.view[]] Serving /api/error/all to * (auth: True)",
#                                         # When tuya servers are down
#                                         "*WARNING*[[]tuyaha.tuyaapi[]] request error, status code is 5*, device *",
#                                         # Sometimes xiaomi gateway looses connection to wifi
#                                         "*ERROR*[[]xiaomi_gateway[]] Cannot connect to Gateway",
#                                         "*ERROR*[[]xiaomi_gateway[]] No data in response from hub None"],
#         # Error on start after reboot
#         'mosquitto': ["*: Socket error on client <unknown>, disconnecting."],
#         'syncthing': ["* INFO: Failed to exchange Hello messages with * at *: EOF"],
#         # Error on start. Can be safely ignored
#         'letsencrypt': ["*activation of module imklog failed*"],
#         # Warnings on start that we can safely ignore
#         'owncloud_mysql': ["* 0 [[]Warning[]] '*' entry '*' ignored in --skip-name-resolve mode.",
#                           "* 0 [[]Warning[]] Failed to set up SSL because of the following SSL library error: SSL context is not usable without certificate and private key",
#                           "* 0 [[]Warning[]] TIMESTAMP with implicit DEFAULT value is deprecated. Please use --explicit_defaults_for_timestamp server option (see documentation for more details)."],
#         'fail2ban': ["*fail2ban.actions: WARNING * Ban *"],
#         # Log about message dispatch, contains message title, which can include "Error ..." word
#         'mail_alt': ["*<= * H=(localhost) [[]*[]] P=esmtp S=* T=* for *"],
#         # Warnings about unsupported features on init
#         'dockerd': ["*failed to load plugin io.containerd.snapshotter.v1.btrfs*",
#                    "*could not use snapshotter btrfs in metadata plugin*",
#                    "*Your kernel does not support swap memory limit*",
#                    "*Your kernel does not support cgroup rt period*",
#                    "*Your kernel does not support cgroup rt runtime*",
#                    # Errors related, probably, to some wrongly removed containers. Doesn't cause problems
#                    "*migrate container error: open /var/lib/docker/containers/dc8bc204726549661c57f60aceac794c3538d842c0eae0477a455c32ff2da053/config.json: no such file or directory*",
#                    "*Failed to load container mount *: mount does not exist*",
#                    "*Failed to load container dc8bc204726549661c57f60aceac794c3538d842c0eae0477a455c32ff2da053: open *: no such file or directory*",
#                    "*No such container: 600739b5e323ff2153b50377761957bc43475449d61c309c6301716c4cc19096*",
#                    "*Couldn't run auplink before unmount *: signal: segmentation fault (core dumped)*"],
#         'dashboard': ["[[]dashboard: main[]] [[]job: weather[]] * <error> executed with errors: HTTP error (500 Internal Server Error) (in scheduler.js:37)",
#                      "    at handleError (/home/dashboard/src/node_modules/atlasboard/lib/scheduler.js:37:29)"]}
# [nginx-404] Ignore 192.168.0.10 by ip
# include = {'fail2ban': ['] Ignore ']}
# syslog_identifiers = ['duplicity', 'dockerd']

class LogTrigger:

    def __init__(self, config):
        self.server = None

        self.mail_config = dict(config.items('Mail'))
        self.sender_name = self.mail_config.get('sender_name') or 'Log Trigger'
        self.sender_email = self.mail_config.get('sender_email') or socket.gethostname()
        self.to = self.mail_config['to']
        self.mail_server_host = self.mail_config['server_host']
        self.mail_server_port = self.mail_config.get('server_port') or 25
        
        self.main_config = dict(config.items('Main'))
        self.generic_erroneous_match = re.compile(self.main_config.get('generic_erroneous_match', 'a^'), re.IGNORECASE) # a^ - matches nothing
        self.syslog_identifiers = self.main_config.get('syslog_identifiers_watch', '').split(',')
        self.ignored_containers = self.main_config.get('ignored_containers', '').split(',')
        
        self.include = self.section_to_dict(config.items('Always Include'), 'match_')
        self.ignore = self.gen_ignore_matchers(config.items('Ignore'))
        self.level_getters = self.gen_level_getters(config.items('Levels'))
        self.erroneous_levels = self.gen_erroneous_levels(config.items('Levels'))
        
        self.files = json.loads(config.get("Watch files", "files", fallback="[]"))

    def is_erroneous_message(self, service, message):
        matcher = self.level_getters.get(service)
        if matcher:
            match = matcher.search(message)
            if match:
                level = match.group(1)
                return level in self.erroneous_levels[service]
        
        if self.generic_erroneous_match.search(message):
            return True

        return False

    def is_service_message_ignore(self, service, message):
        to_ignore = self.ignore.get(service)
        if to_ignore:
            for matcher in to_ignore:
                if matcher.search(message):
                    return True

        return False

    def gen_level_getters(self, section):
        level_getters = self.section_to_dict(section, 'levels_match_')
        for service in level_getters:
            level_getters[service] = re.compile(level_getters[service])

        return level_getters

    def gen_ignore_matchers(self, section):
        ignore_list = self.section_to_dict(section, 'match_')
        ignore_matchers = {}
        for service, matchers in ignore_list.items():
            ignore_matchers[service] = list(map(re.compile, matchers.split('\n')))

        return ignore_matchers

    def gen_erroneous_levels(self, section):
        erroneous_levels = self.section_to_dict(section, 'erroneous_levels_')
        for service in erroneous_levels:
            erroneous_levels[service] = erroneous_levels[service].split(',')

        return erroneous_levels

    def section_to_dict(self, section, prefix):
        res = {}
        for key, value in dict(section).items():
            if not prefix in key:
                continue
            service = key.replace(prefix, '')
            res[service] = value
        
        return res

    def init_logging(self):
        # DEBUG/INFO to stdout, WARNING+ to stderr (http://stackoverflow.com/a/16066513/782599)
        class InfoFilter(logging.Filter):
            def filter(self, rec):
                return rec.levelno in (logging.DEBUG, logging.INFO)

        self.logger = logging.getLogger('__name__')
        self.logger.setLevel(logging.DEBUG)

        h1 = logging.StreamHandler(sys.stdout)
        h1.setLevel(logging.DEBUG)
        h1.addFilter(InfoFilter())
        h2 = logging.StreamHandler()
        h2.setLevel(logging.WARNING)

        formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
        h1.setFormatter(formatter)
        h2.setFormatter(formatter)

        self.logger.addHandler(h1)
        self.logger.addHandler(h2)


    def server_reconnect(self):
        if self.server is not None:
            self.server.quit()
        self.server = smtplib.SMTP(self.mail_server_host, self.mail_server_port)
        self.server.ehlo()

    def send_email(self, title, text):
        msg = MIMEText(text)
        msg['Subject'] = title
        msg['From'] = '%s <%s>' % (self.sender_name, self.sender_email)
        msg['To'] = self.to
        try:
            self.server.sendmail(self.sender_email, self.to, msg.as_string())
        except:
            self.logger.error('Failed to send email: \n%s. %s', sys.exc_info()[0], sys.exc_info()[1])
            self.server_reconnect()


    def is_ignore(self, info):
        if info['CONTAINER_NAME'] in self.ignored_containers:
            self.logger.debug('Ignore, ignored containers (%s)' % info['CONTAINER_NAME'])
            return True
        for container in self.include:
            for string in self.include[container]:
                if string in info['MESSAGE']:
                    self.logger.debug("Don't ignore, always include (%s)" % string)
                    return False
        if self.is_service_message_ignore(info['CONTAINER_NAME'], info['MESSAGE']):
            self.logger.debug('Ignore, per-container matcher')
            return True
        if not self.is_erroneous_message(info['CONTAINER_NAME'], info['MESSAGE']):
            self.logger.debug('Ignore, not erroneous message')
            return True
        
        return False


    def parse(self, info):
        if not isinstance(info['MESSAGE'], list):
            return info
        # journald converts message to utf-8 byte array, if it was coloured output from program
        # convert it back to utf-8 string + remove colour codes
        info['MESSAGE'] = ansi_escape.sub('', bytes(info['MESSAGE']).decode('utf-8'))
        return info

    async def watch_file(self, path):
        self.logger.info('Track file: %s' % path)
        f = open(path, mode='r', errors='replace')
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if not line:
                await asyncio.sleep(1)
                continue
            line = line.rstrip('\n')
            self.logger.info('New log in "%s": "%s"' % (path, line))
            self.send_email('New log in file "%s"' % path, "```\n%s\n```" % line)

    async def watch_files(self):
        futures = []
        for path in self.files:
            futures.append(self.watch_file(path))
        if len(futures):
            await asyncio.wait(futures)

    def journald_reader(self):
        line = sys.stdin.readline()
        info = json.loads(line)
        if info.get('SYSLOG_IDENTIFIER') in self.syslog_identifiers:
            info['CONTAINER_NAME'] = info['SYSLOG_IDENTIFIER']
        if 'CONTAINER_NAME' not in info:
            return False
        info = self.parse(info)
        if self.is_ignore(info):
            return False
        self.logger.info('Error in container "%s": "%s"' % (info['CONTAINER_NAME'], info['MESSAGE']))
        self.send_email('Error on %s in container "%s"' % (info['_HOSTNAME'], info['CONTAINER_NAME']), "```\n%s\n```" %
            info['MESSAGE'])

    def signal_handler(self, loop):
        loop.remove_signal_handler(signal.SIGTERM)
        loop.stop()

    def main(self):
        self.init_logging()
        self.server_reconnect()

        loop = asyncio.get_event_loop()

        # Watch journald
        loop.add_reader(sys.stdin.fileno(), self.journald_reader)

        # Watch files
        asyncio.ensure_future(self.watch_files(), loop=loop)

        loop.add_signal_handler(signal.SIGTERM, self.signal_handler, loop)

        loop.run_forever()

if __name__ == '__main__':
    config = configparser.ConfigParser()
    config.read(sys.argv[1])
    log_trigger = LogTrigger(config)
    log_trigger.main()
