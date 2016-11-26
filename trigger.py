#!/usr/bin/env python
import sys, json, logging, smtplib
from email.mime.text import MIMEText

email_host = 'exim'
email_port = 25
sender = 'journald@sr-server.home.annekov.com'
to = 'paul.annekov@gmail.com'

logger = None

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
    print title
    print text
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

init_logging()

for line in sys.stdin:
    info = json.loads(line)
    if int(info['PRIORITY']) > 3:
        continue
    send_email('Error on %s in container "%s"' % (info['_HOSTNAME'], info['CONTAINER_NAME']), "Error:\n%s" %
       info['MESSAGE'])
