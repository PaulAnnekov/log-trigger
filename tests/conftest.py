import pytest
import configparser
import smtplib

@pytest.fixture
def config():
    config = configparser.ConfigParser()
    config['Mail'] = {
        'to': 'test_to',
        'sender_email': 'log_trigger_server',
        'server_host': 'test_host',
    }
    config['Main'] = {}
    config['Levels'] = {}
    config['Always Include'] = {}
    config['Ignore'] = {}

    return config

@pytest.fixture
def patch_smtp(mocker):
    mocker.patch.object(smtplib.SMTP, '__init__', return_value=None)
    mocker.patch.object(smtplib.SMTP, 'ehlo', autospec=True)
    mocker.patch.object(smtplib.SMTP, 'sendmail', autospec=True)
