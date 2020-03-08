from log_trigger import LogTrigger

def test_simple(monkeypatch, patch_smtp, config):
    config['Main'] = {
        'generic_erroneous_match': 'error|exception'
    }

    container_name = 'test_container'

    monkeypatch.setattr('sys.stdin.readline', lambda: '{"CONTAINER_NAME": "%s", "MESSAGE": "error", "_HOSTNAME": "test_host"}' % container_name)
    
    log_trigger = LogTrigger(config)
    log_trigger.init_logging()
    log_trigger.server_reconnect()

    assert log_trigger.journald_reader() == None
    log_trigger.server.sendmail.assert_called_once_with(
        log_trigger.server, 
        config['Mail']['sender_email'], 
        config['Mail']['to'], 
        """Content-Type: text/plain; charset="us-ascii"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit
Subject: Error on %s in container "%s"
From: Log Trigger <%s>
To: %s

```
error
```""" % (config['Mail']['server_host'], container_name, config['Mail']['sender_email'], config['Mail']['to'])
    )


def test_no_error(monkeypatch, patch_smtp, config):
    config['Main'] = {
        'generic_erroneous_match': 'error|exception'
    }

    container_name = 'test_container'

    monkeypatch.setattr('sys.stdin.readline', lambda: '{"CONTAINER_NAME": "%s", "MESSAGE": "INFO", "_HOSTNAME": "test_host"}' % container_name)
    
    log_trigger = LogTrigger(config)
    log_trigger.init_logging()
    log_trigger.server_reconnect()

    assert log_trigger.journald_reader() == False
    log_trigger.server.sendmail.assert_not_called()

# Message matches generic matcher, but doesn't match level matcher, should ignore
def test_ignore_per_service_level_matcher(monkeypatch, patch_smtp, config):
    config['Main'] = {
        'generic_erroneous_match': 'error|exception',
    }
    config['Levels'] = {
        'levels_match_syncthing': '.* (VERBOSE|DEBUG|INFO|WARNING): .*',
        'erroneous_levels_syncthing': 'WARNING'
    }

    container_name = 'syncthing'

    monkeypatch.setattr('sys.stdin.readline', lambda: '{"CONTAINER_NAME": "%s", "MESSAGE": "[JTHR2] 19:13:24 INFO: Connection to 70CDAC6A-6144-11EA-BC55-0242AC130003 at [::]:22000-75.123.123.1232:22000/quic-client/TLS1.3-TLS_AES_128_GCM_SHA256 closed: reading length: NO_ERROR: No recent network activity", "_HOSTNAME": "test_host"}' % container_name)
    
    log_trigger = LogTrigger(config)
    log_trigger.init_logging()
    log_trigger.server_reconnect()

    assert log_trigger.journald_reader() == False
    log_trigger.server.sendmail.assert_not_called()


# Message matches level matcher, must send an email
def test_use_per_service_level_matcher(monkeypatch, patch_smtp, config):
    config['Levels'] = {
        'levels_match_home_assistant': '.* (DEBUG|INFO|WARNING|ERROR|CRITICAL) .*',
        'erroneous_levels_home_assistant': 'WARNING,ERROR,CRITICAL'
    }

    container_name = 'home_assistant'

    monkeypatch.setattr('sys.stdin.readline', lambda: '{"CONTAINER_NAME": "%s", "MESSAGE": "2020-02-23 03:52:16 ERROR (SyncWorker_9) [roomba.roomba] Error: [Errno 113] Host is unreachable", "_HOSTNAME": "test_host"}' % container_name)
    
    log_trigger = LogTrigger(config)
    log_trigger.init_logging()
    log_trigger.server_reconnect()

    assert log_trigger.journald_reader() == None
    log_trigger.server.sendmail.assert_called_once_with(
        log_trigger.server, 
        config['Mail']['sender_email'], 
        config['Mail']['to'], 
        """Content-Type: text/plain; charset="us-ascii"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit
Subject: Error on %s in container "%s"
From: Log Trigger <%s>
To: %s

```
2020-02-23 03:52:16 ERROR (SyncWorker_9) [roomba.roomba] Error: [Errno 113] Host is unreachable
```""" % (config['Mail']['server_host'], container_name, config['Mail']['sender_email'], config['Mail']['to'])
    )


def test_ignore(monkeypatch, patch_smtp, config):
    config['Levels'] = {
        'levels_match_home_assistant': '.* (DEBUG|INFO|WARNING|ERROR|CRITICAL) .*',
        'erroneous_levels_home_assistant': 'WARNING,ERROR,CRITICAL'
    }
    config['Ignore'] = {
        'match_home_assistant': '\\[homeassistant\\.components\\.vacuum\\] Platform roomba not ready yet\\. Retrying in .* seconds\\.'
    }

    container_name = 'home_assistant'

    monkeypatch.setattr('sys.stdin.readline', lambda: '{"CONTAINER_NAME": "%s", "MESSAGE": "2020-02-23 04:27:03 WARNING (MainThread) [homeassistant.components.vacuum] Platform roomba not ready yet. Retrying in 180 seconds.", "_HOSTNAME": "test_host"}' % container_name)
    
    log_trigger = LogTrigger(config)
    log_trigger.init_logging()
    log_trigger.server_reconnect()

    assert log_trigger.journald_reader() == False
    log_trigger.server.sendmail.assert_not_called()


# Message matches always include, should send email
def test_always_include(monkeypatch, patch_smtp, config):
    config['Main'] = {
        'generic_erroneous_match': 'error|exception'
    }
    config['Always Include'] = {
        'match_fail2ban': '] Ignore' 
    }

    container_name = 'fail2ban'

    monkeypatch.setattr('sys.stdin.readline', lambda: '{"CONTAINER_NAME": "%s", "MESSAGE": "2020-02-19 00:20:30,323 fail2ban.filter         [10]: INFO    [nginx-404] Ignore 172.17.0.1 by ip", "_HOSTNAME": "test_host"}' % container_name)
    
    log_trigger = LogTrigger(config)
    log_trigger.init_logging()
    log_trigger.server_reconnect()

    assert log_trigger.journald_reader() == None
    log_trigger.server.sendmail.assert_called_once_with(
        log_trigger.server, 
        config['Mail']['sender_email'], 
        config['Mail']['to'], 
        """Content-Type: text/plain; charset="us-ascii"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit
Subject: Error on %s in container "%s"
From: Log Trigger <%s>
To: %s

```
2020-02-19 00:20:30,323 fail2ban.filter         [10]: INFO    [nginx-404] Ignore 172.17.0.1 by ip
```""" % (config['Mail']['server_host'], container_name, config['Mail']['sender_email'], config['Mail']['to'])
    )
