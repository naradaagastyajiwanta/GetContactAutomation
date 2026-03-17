import subprocess
output = subprocess.check_output(['docker', 'logs', 'gc-orchestrator', '--tail', '2000'], text=True)
for x in output.split('\n'):
    if 'rejected' in x or 'picking' in x:
        print(x)
