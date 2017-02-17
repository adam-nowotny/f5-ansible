#!/usr/bin/python
#
# Copyright 2017 F5 Networks Inc.
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

ANSIBLE_METADATA = {'status': ['preview'],
                    'supported_by': 'community',
                    'version': '1.0'}

DOCUMENTATION = '''
module: bigip_snmp_contact
short_description: Manipulate SNMP contact information on a BIG-IP.
description:
  - Manipulate SNMP contact information on a BIG-IP.
version_added: 2.3
options:
  name:
    description:
      - Name of the SNMP configuration endpoint.
    required: True
  snmp_version:
    description:
      - Specifies to which Simple Network Management Protocol (SNMP) version
        the trap destination applies.
    required: False
    default: None
    choices:
      - 1
      - 2c
  community:
    description:
      - Specifies the community name for the trap destination.
    required: False
    default: None
  destination:
    description:
      - Specifies the address for the trap destination. This can be either an
        IP address or a hostname.
    required: False
    default: None
  port:
    description:
      - Specifies the port for the trap destination.
    required: False
    default: None
  network:
    description:
      - Specifies the trap network.
    required: False
    default: None
    choices:
      - other
      - management
      - default
  state:
    description:
      - When C(present), ensures that the cloud connector exists. When
        C(absent), ensures that the cloud connector does not exist.
    required: False
    default: present
    choices:
      - present
      - absent
notes:
  - Requires the f5-sdk Python package on the host. This is as easy as pip
    install f5-sdk.
  - This module only supports version v1 and v2c of SNMP.
extends_documentation_fragment: f5
requirements:
    - f5-sdk >= 2.2.0
    - ansible >= 2.3.0
author:
    - Tim Rupp (@caphrim007)
'''

EXAMPLES = '''

'''

RETURN = '''

'''

from ansible.module_utils.f5_utils import *


class Parameters(AnsibleF5Parameters):
    api_param_map = dict(
        snmp_version='version',
        community='community',
        destination='host',
        port='port',
        network='network'
    )

    def __init__(self, params=None):
        self._network = None
        super(Parameters, self).__init__(params)

    @property
    def network(self):
        if self._network is None:
            return None
        network = str(self._network)
        if network == 'management':
            return 'mgmt'
        else:
            return network

    @network.setter
    def network(self, value):
        self._network = value

    @classmethod
    def from_api(cls, params):
        for key,value in iteritems(cls.api_param_map):
            param = params.pop(value, None)
            if param is not None:
                param = str(param)
            params[key] = param
        p = cls(params)
        return p

    def api_params(self):
        params = super(Parameters, self).api_params()
        if self.network == 'default':
            params.update({'network': None})
        return params


class ModuleManager(object):
    def __init__(self, client):
        self.client = client
        self.have = None
        self.want = Parameters(self.client.module.params)
        self.changes = Parameters()

    def exec_module(self):
        if not HAS_F5SDK:
            raise F5ModuleError("The python f5-sdk module is required")

        changed = False
        result = dict()
        state = self.want.state

        try:
            if state == "present":
                changed = self.present()
            elif state == "absent":
                changed = self.absent()
        except iControlUnexpectedHTTPError as e:
            raise F5ModuleError(str(e))

        #result.update(**self.changes)
        result.update(dict(changed=changed))
        return result

    def exists(self):
        return self.client.api.tm.sys.snmp.traps_s.trap.exists(
            name=self.want.name,
            partition=self.want.partition
        )

    def present(self):
        if self.exists():
            return self.update()
        else:
            return self.create()

    def create(self):
        required_resources = [
            'version', 'community', 'destination', 'port', 'network'
        ]

        if self.client.check_mode:
            return True

        if all(getattr(self.want, v) is None for v in required_resources):
            raise F5ModuleError(
                "You must specify at least one of "
                + ', '.join(required_resources)
            )
        self.create_on_device()
        return True

    def should_update(self):
        updateable = Parameters.api_param_map.keys()

        for key in updateable:
            if getattr(self.want, key) is not None:
                attr1 = getattr(self.want, key)
                attr2 = getattr(self.have, key)
                if attr1 != attr2:
                    setattr(self.changes, key, getattr(self.want, key))
                    return True

    def update(self):
        self.have = self.read_current_from_device()
        if not self.should_update():
            return False
        if self.client.check_mode:
            return True
        self.update_on_device()
        return True

    def update_on_device(self):
        params = self.want.api_params()
        result = self.client.api.tm.sys.snmp.traps_s.trap.load(
            name=self.want.name,
            partition=self.want.partition
        )
        result.modify(**params)

    def read_current_from_device(self):
        result = self.client.api.tm.sys.snmp.traps_s.trap.load(
            name=self.want.name,
            partition=self.want.partition
        ).to_dict()
        result.pop('_meta_data', None)

        # BIG-IP's value for "default" is that the key does not
        # exist. This conflicts with our purpose of having a key
        # not exist (which we equate to "i dont want to change that"
        # therefore, if we load the information from BIG-IP and
        # find that there is no 'network' key, that is BIG-IP's
        # way of saying that the network value is "default"
        if 'network' not in result:
            result['network'] = 'default'
        return Parameters.from_api(result)

    def create_on_device(self):
        params = self.want.api_params()
        self.client.api.tm.sys.snmp.traps_s.trap.create(
            name=self.want.name,
            partition=self.want.partition,
            **params
        )

    def absent(self):
        if self.exists():
            return self.remove()
        return False

    def remove(self):
        if self.client.check_mode:
            return True
        self.remove_from_device()
        if self.exists():
            raise F5ModuleError("Failed to delete the snmp trap")
        return True

    def remove_from_device(self):
        result = self.client.api.tm.sys.snmp.traps_s.trap.load(
            name=self.want.name,
            partition=self.want.partition
        )
        if result:
            result.delete()


class ArgumentSpec(object):
    def __init__(self):
        self.supports_check_mode = True
        self.argument_spec = dict(
            name=dict(
                required=True
            ),
            snmp_version=dict(
                required=False,
                default=None,
                choices=['1','2c']
            ),
            community=dict(
                required=False,
                default=None
            ),
            destination=dict(
                required=False,
                default=None
            ),
            port=dict(
                required=False,
                default=None
            ),
            network=dict(
                required=False,
                default=None,
                choices=['other', 'management', 'default']
            ),
            state=dict(
                required=False,
                default='present',
                choices=['absent', 'present']
            )
        )
        self.f5_product_name = 'bigip'


def main():
    spec = ArgumentSpec()

    client = AnsibleF5Client(
        argument_spec=spec.argument_spec,
        supports_check_mode=spec.supports_check_mode,
        f5_product_name=spec.f5_product_name
    )

    mm = ModuleManager(client)
    results = mm.exec_module()
    client.module.exit_json(**results)

if __name__ == '__main__':
    main()
