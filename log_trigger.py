#!/usr/bin/env python3
import sys, json, logging, smtplib, configparser, re, fnmatch, time, os, asyncio
from email.mime.text import MIMEText

logger = None

config = configparser.ConfigParser()
config.read(sys.argv[1])
mail_config = dict(config.items('Mail'))
sender = mail_config['sender']
to = mail_config['to']
email_host = 'mail'
email_port = 25

files = json.loads(config.get("Watch files", "files", fallback="[]"))

ansi_escape = re.compile(r'(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]')
# https://stackoverflow.com/questions/2595119/python-glob-and-bracket-characters
ignore = {'smarthome_home_assistant_1': ["*[[]custom_components.device_tracker.padavan_tracker[]] Can't get connected "
                                        "clients: Can't connect to router: HTTPConnectionPool(host='192.168.0.21', "
                                        "port=80): Max retries exceeded with url: /Main_WStatus*_Content.asp (Caused "
                                        "by ConnectTimeoutError(<requests.packages.urllib3.connection.HTTPConnection "
                                        "object at *>, 'Connection to 192.168.0.21 timed out. "
                                        "(connect timeout=1)'))*",
                                        "*[[]custom_components.device_tracker.padavan_tracker[]] Can't get connected "
                                        "clients: Some error during request: HTTPConnectionPool(host='192.168.0.21', "
                                        "port=80): Read timed out. (read timeout=1)*",
                                        "*[[]roomba.roomba.Roomba[]]*\"error\":0,*",
                                        "*[[]homeassistant.helpers.entity[]] Update of * is taking over 10 seconds",
                                        "*[[]PyXiaomiGateway[]] No data in response from hub None",
                                        "*[[]PyXiaomiGateway[]] Non matching response. Expecting read_ack, but got write_ack",
                                        "*[[]PyXiaomiGateway[]] Non matching response. Expecting write_ack, but got read_ack",
                                        "*[[]homeassistant.components.http[]] Serving /api/error/all to*",
                                        "*[[]homeassistant.components.emulated_hue[]] When targeting Google Home, listening port has to be port 80",
                                        "*[[]homeassistant.components.recorder[]] Ended unfinished session (*)",
                                        "*[[]homeassistant.components.updater[]] Running on 'dev', only analytics will be submitted",
                                        "*[[]xiaomi_gateway[]] No data in response from hub None",
                                        "*[[]xiaomi_gateway[]] Cannot connect to Gateway",
                                        "*[[]xiaomi_gateway[]] Non matching response. Expecting write_ack, but got read_ack",
                                        "*[[]xiaomi_gateway[]] Non matching response. Expecting read_ack, but got write_ack",
                                        # Ignore system_log_event event and mqtt service which sends this event to mqtt server
                                        "*[[]homeassistant.core[]] Bus:Handling <Event *system_log_event*",
                                        # Z-wave component has service names and data with trigger words, filter them
                                        "*INFO*[[]homeassistant.core[]]*service_registered*replace_failed_node*",
                                        "*INFO*[[]homeassistant.core[]]*service_registered*remove_failed_node*",
                                        "*INFO*[[]homeassistant.core[]]*state_changed*zwave._*is_failed*"],
        'fail2ban': ["*fail2ban.actions: WARNING * Ban *"]}
# [nginx-404] Ignore 192.168.0.10 by ip
include = {'fail2ban': ['] Ignore ']}
syslog_identifiers = ['duplicity']

def init_logging():
    global logger

    # DEBUG/INFO to stdout, WARNING+ to stderr (http://stackoverflow.com/a/16066513/782599)
    class InfoFilter(logging.Filter):
        def filter(self, rec):
            return rec.levelno in (logging.DEBUG, logging.INFO)

    logger = logging.getLogger('__name__')
    logger.setLevel(logging.DEBUG)

    h1 = logging.StreamHandler(sys.stdout)
    h1.setLevel(logging.DEBUG)
    h1.addFilter(InfoFilter())
    h2 = logging.StreamHandler()
    h2.setLevel(logging.WARNING)

    formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
    h1.setFormatter(formatter)
    h2.setFormatter(formatter)

    logger.addHandler(h1)
    logger.addHandler(h2)


def send_email(title, text):
    msg = MIMEText(text)
    msg['Subject'] = title
    msg['From'] = 'Log trigger <%s>' % sender
    msg['To'] = to
    server = None
    try:
        server = smtplib.SMTP(email_host, email_port)
        server.ehlo()
        server.sendmail(sender, to, msg.as_string())
    except:
        if server is not None:
            server.quit()
        logger.error('Failed to send email: \n%s. %s', sys.exc_info()[0], sys.exc_info()[1])


def is_ignore(info):
    if info['CONTAINER_NAME'] in ['log-trigger', 'mail']:
        return True
    for container in include:
        for string in include[container]:
            if string in info['MESSAGE']:
                return False
    # [WRN] and [ERR] are statuses of motion.log
    if not any(marker in info['MESSAGE'].lower() for marker in ['error', 'exception', 'unexpected', 'failed',
                                                                '[wrn]', '[err]', 'warning']):
        return True
    for container in ignore:
        for error in ignore[container]:
            if fnmatch.fnmatch(info['MESSAGE'], error):
                return True
    return False


def parse(info):
    if not isinstance(info['MESSAGE'], list):
        return info
    # journald converts message to utf-8 byte array, if it was coloured output from program
    # convert it back to utf-8 string + remove colour codes
    info['MESSAGE'] = ansi_escape.sub('', bytes(info['MESSAGE']).decode('utf-8'))
    return info

async def watch_file(path):
    logger.info('Track file: %s' % path)
    f = open(path, mode='r', errors='replace')
    f.seek(0, os.SEEK_END)
    while True:
        line = f.readline()
        if not line:
            await asyncio.sleep(1)
            continue
        line = line.rstrip('\n')
        logger.info('New log in "%s": "%s"' % (path, line))
        send_email('New log in file "%s"' % path, "```\n%s\n```" % line)

async def watch_files():
    futures = []
    for path in files:
        futures.append(watch_file(path))
    if len(futures):
        await asyncio.wait(futures)

def journald_reader():
    line = sys.stdin.readline()
    info = json.loads(line)
    if info.get('SYSLOG_IDENTIFIER') in syslog_identifiers:
        info['CONTAINER_NAME'] = info['SYSLOG_IDENTIFIER']
    if 'CONTAINER_NAME' not in info:
        return
    info = parse(info)
    if is_ignore(info):
        return
    logger.info('Error in container "%s": "%s"' % (info['CONTAINER_NAME'], info['MESSAGE']))
    send_email('Error on %s in container "%s"' % (info['_HOSTNAME'], info['CONTAINER_NAME']), "```\n%s\n```" %
    info['MESSAGE'])

def main():
    init_logging()

    loop = asyncio.get_event_loop()

    # Watch journald
    loop.add_reader(sys.stdin.fileno(), journald_reader)

    # Watch files
    asyncio.ensure_future(watch_files(), loop=loop)

    loop.run_forever()

main()
