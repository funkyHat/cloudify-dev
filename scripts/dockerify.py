#!/usr/bin/env python
########
# Copyright (c) 2016 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.

from __future__ import print_function

import argparse
import os
from functools import partial
from subprocess import check_call, check_output, CalledProcessError
from time import sleep

import yaml


EXPOSE = [22, 80, 443, 5671]
PUBLISH = ['80:80', '443:443', '5671:5671']


def main(args=None):
    parser = argparse.ArgumentParser(
        description="Deploy a simple manager blueprint "
                    "into a local docker container",
        )
    parser.add_argument('path', nargs='?', default='.')
    parser.add_argument(
        '--docker_context',
        default=os.path.join(os.path.dirname(__file__), 'dockerify'),
        )
    parser.add_argument(
        '--docker_tag',
        default='cloudify/centos-manager:7',
        )
    parser.add_argument(
        '--ssh-key',
        default=os.path.expanduser('~/.ssh/id_rsa'),
        )
    parser.add_argument(
        '--dockerfile',
        default='https://github.com/CentOS/sig-cloud-instance-images/blob/'
                '9681bb924c70a60dc4042dbc5fc3ed6c27aa3e1c/docker/Dockerfile',
        )
    args = parser.parse_args(args)

    if not os.path.isfile(args.ssh_key):
        raise ValueError(
            "you need to create an SSH key (see man ssh-keygen) first")

    id, ip = create_container(args.docker_context, args.docker_tag)
    print("Created container: " + id)

    ssh_swap(id, ip, args.ssh_key)

    install(args.path, id, ip, args.ssh_key)


def create_container(context, tag):
    # Ensure the image is up to date
    docker.build(['-t', tag, context])

    # Create the container
    container_id = docker.run(
            ['--privileged', '--detach'] +
            ['-e{}'.format(p) for p in EXPOSE] +
            ['-p{}'.format(p) for p in PUBLISH] +
            [tag],
            ).strip()

    container_ip = docker.inspect([
        '--format={{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}',
        container_id,
        ]).strip()

    return container_id, container_ip


def _wait_for_file(container_id, file):
    attempt = 0
    while attempt < 100:
        try:
            return getattr(docker, 'exec')([container_id, 'cat', file])
        except CalledProcessError as e:
            if e.returncode != 1:
                # Some error other than not found. Bad!
                raise
            attempt += 1
            sleep(0.1)
    raise


def ssh_swap(id, ip, keyname):
    """
    You get the host key in, the client key out
    in out in out shake it all about
    """
    server_pubkey_file = '/etc/ssh/ssh_host_rsa_key'
    # once this file exists the SSHD in the container is sufficiently ready
    server_pubkey = _wait_for_file(id, server_pubkey_file)
    with open(os.path.expanduser('~/.ssh/known_hosts'), 'w+') as f:
        f.write('{ip} ssh-rsa {key}\n'.format(
                ip=ip,
                key=server_pubkey))

    # new container shouldn't have an authorized_keys file yet
    try:
        docker.exc([id, 'mkdir', '-m700', '/root/.ssh'])
    except CalledProcessError as e:
        if e.returncode != 1:
            raise
        # Hopefully that means it's already there
    docker.cp([
            keyname + '.pub',
            '{id}:/root/.ssh/authorized_keys'.format(id=id)
            ])


def install(path, id, ip, key_filename):

    # Write the inputs file
    with open('docker-bootstrap-inputs.yaml', 'w') as f:
        f.write(yaml.safe_dump({
                    'public_ip': ip,
                    'private_ip': ip,
                    'ssh_user': 'root',
                    'ssh_key_filename': key_filename,
                    },
                allow_unicode=True))

    # Clean the environment
    check_output(['cfy', 'init', '-r'])

    # Bootstrap the manager
    check_call([
            'cfy', 'bootstrap', '--install-plugins',
            '-p', path,
            '-i', 'docker-bootstrap-inputs.yaml'])


class docker(object):
    """Helper for running docker commands"""
    def _action(self, action, options, *args, **kwargs):
        if action == 'exc':
            # Because `exec` is a keyword in Python2
            action = 'exec'
        return check_output(
                ['docker', action] + options,
                *args, **kwargs)

    def __getattr__(self, attr):
        """return a function that will run the named command"""
        return partial(self._action, attr)


docker = docker()


if __name__ == "__main__":
    main()
