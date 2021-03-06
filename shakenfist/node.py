from functools import partial
import time

from shakenfist import baseobject
from shakenfist.config import config
from shakenfist import etcd
from shakenfist import logutil
from shakenfist import util


LOG, _ = logutil.setup(__name__)


class Node(baseobject.DatabaseBackedObject):
    object_type = 'node'
    current_version = 2

    # docs/development/state_machine.md has a description of these states.
    STATE_CREATED = 'created'
    STATE_ERROR = 'error'
    STATE_DELETED = 'deleted'
    STATE_MISSING = 'missing'

    state_targets = {
        None: (STATE_CREATED, STATE_ERROR, STATE_MISSING),
        STATE_CREATED: (STATE_DELETED, STATE_ERROR, STATE_MISSING),
        STATE_ERROR: (STATE_ERROR, STATE_DELETED),
        STATE_MISSING: (STATE_CREATED, STATE_ERROR)
    }

    def __init__(self, static_values):
        # We treat a node name as a UUID here for historical reasons
        super(Node, self).__init__(static_values['fqdn'],
                                   static_values.get('version'))

        self.__ip = static_values['ip']

    @classmethod
    def new(cls, name, ip):
        n = Node.from_db(name)
        if n:
            return n

        Node._db_create(name, {
            'fqdn': name,
            'ip': ip,
            'version': cls.current_version
        })
        n = Node.from_db(name)
        n.state = cls.STATE_CREATED
        n.add_event('db record creation', None)
        return n

    @classmethod
    def observe_this_node(cls):
        # We use Node.new here because it acts like a "upsert". It will create
        # the node object if it doesn't already exist, and otherwise use the
        # existing one.
        n = cls.new(config.NODE_NAME, config.NODE_IP)
        n._db_set_attribute('observed',
                            {
                                'at': time.time(),
                                'release': util.get_version()
                            })

    @staticmethod
    def from_db(fqdn):
        if not fqdn:
            return None

        static_values = Node._db_get(fqdn)
        if not static_values:
            return None

        return Node(static_values)

    def external_view(self):
        # If this is an external view, then mix back in attributes that users
        # expect
        return {
            'uuid': self.uuid,
            'fqdn': self.fqdn,
            'ip': self.ip,
            'state': self.state.value,
            'lastseen': self.last_seen,
            'release': self.installed_version
        }

    # Static values
    @property
    def ip(self):
        return self.__ip

    # Values routed to attributes, writes are via helper methods.
    @property
    def last_seen(self):
        return self._db_get_attribute('observed')['at']

    @property
    def installed_version(self):
        return self._db_get_attribute('observed')['release']


class Nodes(baseobject.DatabaseBackedObjectIterator):
    def __iter__(self):
        for _, n in etcd.get_all('node', None):
            n = Node.from_db(n['uuid'])
            if not n:
                continue

            out = self.apply_filters(n)
            if out:
                yield out


active_states_filter = partial(
    baseobject.state_filter, ['created'])
inactive_states_filter = partial(
    baseobject.state_filter, ['deleted', 'error', 'missing'])
