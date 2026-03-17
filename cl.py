import subprocess
output = subprocess.check_output(['docker', 'logs', 'gc-orchestrator', '--tail', '5000'], text=True)
for x in output.split('\n'):
    if 'LinkedIn' in x or 'linkedin' in x:
        if len(x)<200: print(x)

