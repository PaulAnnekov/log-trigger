import pytest
import configparser
import smtplib

@pytest.fixture
def gen_config():
    def _generate_config(text):
        config = configparser.ConfigParser()
        config.read_string(text)
        if not config.has_section('Mail'):
            config['Mail'] = {
                'to': 'test_to',
                'sender_email': 'log_trigger_server',
                'server_host': 'test_host',
            }
        if not config.has_section('Main'):
            config['Main'] = {}
        if not config.has_section('Levels'):
            config['Levels'] = {}
        if not config.has_section('Always Include'):
            config['Always Include'] = {}
        if not config.has_section('Ignore'):
            config['Ignore'] = {}

        return config

    return _generate_config

@pytest.fixture
def patch_smtp(mocker):
    mocker.patch.object(smtplib.SMTP, '__init__', return_value=None)
    mocker.patch.object(smtplib.SMTP, 'ehlo', autospec=True)
    mocker.patch.object(smtplib.SMTP, 'sendmail', autospec=True)
