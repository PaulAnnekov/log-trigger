#!/usr/bin/env python3
import sys, json, signal, logging, smtplib, configparser, re, fnmatch, time, os, asyncio, socket
from email.mime.text import MIMEText

ansi_escape = re.compile(r'(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]')

class LogTrigger:

    def __init__(self, config, cursor_file):
        self.server = None

        self.cursor_file = cursor_file

        self.mail_config = dict(config.items('Mail'))
        self.sender_name = self.mail_config.get('sender_name') or 'Log Trigger'
        self.sender_email = self.mail_config.get('sender_email') or 'log-trigger@%s' % socket.gethostname()
        self.to = self.mail_config['to']
        self.mail_server_host = self.mail_config['server_host']
        self.mail_server_port = self.mail_config.get('server_port') or 25
        
        self.main_config = dict(config.items('Main'))
        self.generic_erroneous_match = re.compile(self.main_config.get('generic_erroneous_match', 'a^'), re.IGNORECASE) # a^ - matches nothing
        self.syslog_identifiers = self.main_config.get('syslog_identifiers_watch', '').split(',')
        self.ignored_containers = self.main_config.get('ignored_containers', '').split(',')
        
        self.include = self.gen_matchers_list(config.items('Always Include'))
        self.ignore = self.gen_matchers_list(config.items('Ignore'))
        self.level_getters = self.gen_level_getters(config.items('Levels'))
        self.erroneous_levels = self.gen_erroneous_levels(config.items('Levels'))
        
        self.files = json.loads(config.get("Watch files", "files", fallback="[]"))

    def cursor_save(self, cursor):
        with open(self.cursor_file, 'w+') as outfile:
            outfile.write(cursor)

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

    def is_service_message_matches(self, matchers, service, message):
        to_ignore = matchers.get(service)
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

    def gen_matchers_list(self, section):
        raw_matchers_list = self.section_to_dict(section, 'match_')
        matchers_list = {}
        for service, matchers in raw_matchers_list.items():
            matchers_list[service] = list(map(re.compile, filter(lambda s: s, matchers.split('\n'))))

        return matchers_list

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
            try:
                self.server.quit()
            except:
                self.logger.warning("Can't quit smtp server:\n%s. %s", sys.exc_info()[0], sys.exc_info()[1])    
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
        if self.is_service_message_matches(self.include, info['CONTAINER_NAME'], info['MESSAGE']):
            self.logger.debug("Don't ignore, always include")
            return False
        if self.is_service_message_matches(self.ignore, info['CONTAINER_NAME'], info['MESSAGE']):
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
        cursor = info.get('__CURSOR')
        if info.get('SYSLOG_IDENTIFIER') in self.syslog_identifiers:
            info['CONTAINER_NAME'] = info['SYSLOG_IDENTIFIER']
        if 'CONTAINER_NAME' not in info:
            self.cursor_save(cursor)
            return False
        info = self.parse(info)
        if self.is_ignore(info):
            self.cursor_save(cursor)
            return False
        self.logger.info('Error in container "%s": "%s"' % (info['CONTAINER_NAME'], info['MESSAGE']))
        self.send_email('Error on %s in container "%s"' % (info['_HOSTNAME'], info['CONTAINER_NAME']), "```\n%s\n```" %
            info['MESSAGE'])
        self.cursor_save(cursor)

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
    log_trigger = LogTrigger(config, sys.argv[2])
    log_trigger.main()
