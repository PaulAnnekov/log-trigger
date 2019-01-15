#!/usr/bin/env python3
import sys, json, signal, logging, smtplib, configparser, re, fnmatch, time, os, asyncio
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
ignore = {'smarthome_home_assistant_1': ["*[[]roomba.roomba.Roomba[]]*\"error\":0,*",
                                        "*[[]homeassistant.helpers.entity[]] Update of * is taking over 10 seconds",
                                        "*[[]homeassistant.components.http[]] Serving /api/error/all to*",
                                        "*[[]homeassistant.components.emulated_hue[]] When targeting Google Home, listening port has to be port 80",
                                        "*[[]homeassistant.components.recorder[]] Ended unfinished session (*)",
                                        "*[[]homeassistant.components.updater[]] Running on 'dev', only analytics will be submitted",
                                        # Ignore system_log_event event and mqtt service which sends this event to mqtt server
                                        "*[[]homeassistant.core[]] Bus:Handling <Event *system_log_event*",
                                        # Z-wave component has service names and data with trigger words, filter them
                                        "*INFO*[[]homeassistant.core[]]*service_registered*replace_failed_node*",
                                        "*INFO*[[]homeassistant.core[]]*service_registered*remove_failed_node*",
                                        "*INFO*[[]homeassistant.core[]]*state_changed*zwave.*is_failed*",
                                        # If robot stuck, "error" field with description will be added
                                        "*INFO*[[]homeassistant.core[]]*state_changed*vacuum.roomba*error*",
                                        # Happens on clean cycle end, it's ok to ignore, it will reconnect
                                        "*WARNING*[[]roomba.roomba.Roomba[]] Unexpected Disconnect From Roomba ! - reconnecting",
                                        # http auth gives this warning if you don't use password
					"*WARNING*[[]homeassistant.components.http[]] You have been advised to set http.api_password.",
    					# HA complains about custom components
  					"*WARNING*[[]homeassistant.loader[]] You are using a custom component for * which has not been tested by Home Assistant. This component might cause stability problems, be sure to disable it if you do experience issues with Home Assistant.",
                                        # Bug https://github.com/home-assistant/home-assistant/issues/17408
                                        "*WARNING*[[]homeassistant.components.binary_sensor.xiaomi_aqara[]] Unsupported movement_type detected: None",
                                        # Called by UI when you open https://smart.home.annekov.com/dev-info page
                                        "*INFO*[[]homeassistant.components.http.view[]] Serving /api/error/all to * (auth: True)"],
        # Error on start after reboot
        'smarthome_mosquitto_1': ["*: Socket error on client <unknown>, disconnecting."],
        # Error on start. Can be safely ignored
        'letsencrypt': ["*activation of module imklog failed*"],
        # Warnings on start that we can safely ignore
        'owncloud_mysql': ["* 0 [[]Warning[]] '*' entry '*' ignored in --skip-name-resolve mode.",
                          "* 0 [[]Warning[]] Failed to set up SSL because of the following SSL library error: SSL context is not usable without certificate and private key",
                          "* 0 [[]Warning[]] TIMESTAMP with implicit DEFAULT value is deprecated. Please use --explicit_defaults_for_timestamp server option (see documentation for more details)."],
        'fail2ban': ["*fail2ban.actions: WARNING * Ban *"],
        # Log about message dispatch, contains message title, which can include "Error ..." word
        'mail_alt': ["*<= * H=(localhost) [[]*[]] P=esmtp S=* T=* for *"],
        # Warnings about unsupported features on init
        'dockerd': ["*failed to load plugin io.containerd.snapshotter.v1.btrfs*",
                   "*could not use snapshotter btrfs in metadata plugin*",
                   "*Your kernel does not support swap memory limit*",
                   "*Your kernel does not support cgroup rt period*",
                   "*Your kernel does not support cgroup rt runtime*",
                   # Errors related, probably, to some wrongly removed containers. Doesn't cause problems
                   "*migrate container error: open /var/lib/docker/containers/dc8bc204726549661c57f60aceac794c3538d842c0eae0477a455c32ff2da053/config.json: no such file or directory*",
                   "*Failed to load container mount *: mount does not exist*",
                   "*Failed to load container dc8bc204726549661c57f60aceac794c3538d842c0eae0477a455c32ff2da053: open *: no such file or directory*",
                   "*No such container: 600739b5e323ff2153b50377761957bc43475449d61c309c6301716c4cc19096*",
                   "*Couldn't run auplink before unmount *: signal: segmentation fault (core dumped)*"
        ]}
# [nginx-404] Ignore 192.168.0.10 by ip
include = {'fail2ban': ['] Ignore ']}
syslog_identifiers = ['duplicity', 'dockerd']

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

def signal_handler(loop):
    loop.remove_signal_handler(signal.SIGTERM)
    loop.stop()

def main():
    init_logging()

    loop = asyncio.get_event_loop()

    # Watch journald
    loop.add_reader(sys.stdin.fileno(), journald_reader)

    # Watch files
    asyncio.ensure_future(watch_files(), loop=loop)

    loop.add_signal_handler(signal.SIGTERM, signal_handler, loop)

    loop.run_forever()

main()
