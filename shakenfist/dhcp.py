# Copyright 2020 Michael Still

import jinja2
import logging
import os
import shutil

from oslo_concurrency import processutils

from shakenfist import config
from shakenfist import util


LOG = logging.getLogger(__file__)
LOG.setLevel(logging.DEBUG)


class DHCP(object):
    def __init__(self, network=None):
        self.network = network

    def __str__(self):
        return str(self.network).replace('network', 'dhcp')

    def make_config(self):
        self.config_dir_path = os.path.join(
            config.parsed.get('STORAGE_PATH'), 'dhcp', self.network.uuid)
        if not os.path.exists(self.config_dir_path):
            LOG.debug('%s: Creating dhcp config at %s' %
                      (self, self.config_dir_path))
            os.makedirs(self.config_dir_path)

        with open(os.path.join(config.parsed.get('STORAGE_PATH'), 'dhcp.tmpl')) as f:
            t = jinja2.Template(f.read())

        subst = self.network.subst_dict()
        c = t.render(subst)

        with open(os.path.join(self.config_dir_path, 'dhcpd.conf'), 'w') as f:
            f.write(c)

    def remove_config(self):
        self.config_dir_path = os.path.join(
            config.parsed.get('STORAGE_PATH'), 'dhcp', self.network.uuid)
        if os.path.exists(self.config_dir_path):
            shutil.rmtree(self.config_dir_path)

    def remove_dhcpd(self):
        subst = self.network.subst_dict()
        processutils.execute(
            'docker rm -f %(dhcp_interface)s' % subst, shell=True, check_exit_code=[0, 1])

    def restart_dhcpd(self):
        self.remove_dhcpd()

        subst = self.network.subst_dict()
        subst['config_dir'] = self.config_dir_path
        processutils.execute(
            'docker run -d --name %(dhcp_interface)s --restart=always '
            '--init --net host -v %(config_dir)s:/data networkboot/dhcpd '
            '%(dhcp_interface)s'
            % subst, shell=True)