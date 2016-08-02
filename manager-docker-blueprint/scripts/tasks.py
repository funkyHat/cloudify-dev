
import os
import yaml

from fabric.api import run, local, lcd


PACKAGES = [
    'libselinux-utils',
    ]


def create(version, manager_ip, key_filename):
    # Versions might be interpreted as numbers by yaml
    version = str(version)

    run('sudo yum install -y {}'.format(' '.join(PACKAGES)))

    with open('docker-bootstrap-inputs.yaml', 'w') as f:
        f.write(yaml.dump({
            'public_ip': manager_ip,
            'private_ip': manager_ip,
            'ssh_user': 'root',
            'ssh_key_filename': key_filename,
            }))

    if not os.path.isfile(version):
        # doesn't exist, treat it as a tag/branch
        local('git clone http://github.com/cloudify-cosmo/cloudify-manager-blueprints.git')
        with lcd('cloudify-manager-blueprints'):
            local('git checkout {}'.format(version))
        version = 'cloudify-manager-blueprints/simple-manager-blueprint.yaml'

    local('cfy bootstrap --install-plugins -p {blueprint} -i {inputs}'.format(
            blueprint=version,
            inputs='docker-bootstrap-inputs.yaml'))


def delete():
    pass
