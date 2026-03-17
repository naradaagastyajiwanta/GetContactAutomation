import subprocess
output = subprocess.check_output(['docker', 'logs', 'gc-orchestrator', '--tail', '2000'], text=True)
found=False
for x in output.split('\n'):
    if 'rejected' in x and 'LinkedIn' in x:
        print(x)
        found=True
if not found: print('NOT REJECTED')
