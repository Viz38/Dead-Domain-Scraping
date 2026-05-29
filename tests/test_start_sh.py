import os

def test_start_sh_no_disable():
    start_sh_path = os.path.join(os.path.dirname(__file__), '..', 'start.sh')
    with open(start_sh_path, 'r') as f:
        content = f.read()
        
    # It should not disable the service on STOP ALL
    assert "sudo systemctl disable ghost-engine.service" not in content, "stop_all_services should not disable the service!"

def test_start_sh_systemd_config():
    start_sh_path = os.path.join(os.path.dirname(__file__), '..', 'start.sh')
    with open(start_sh_path, 'r') as f:
        content = f.read()
        
    # StartLimitIntervalSec=0 should be in [Unit] section, before [Service]
    unit_idx = content.find("[Unit]")
    service_idx = content.find("[Service]")
    limit_idx = content.find("StartLimitIntervalSec=0")
    
    assert unit_idx != -1
    assert service_idx != -1
    assert limit_idx != -1
    
    # Check that StartLimitIntervalSec is between [Unit] and [Service]
    assert unit_idx < limit_idx < service_idx, "StartLimitIntervalSec=0 must be in the [Unit] section!"

