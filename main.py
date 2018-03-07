"""Main module of kytos/mef_eline Kytos Network Application.

NApp to provision circuits from user request.
"""

# import json
# import os
# import pickle
from uuid import uuid4

import requests
from flask import jsonify, request

from kytos.core import KytosNApp, log, rest
from kytos.core.helpers import now
from kytos.core.interface import TAG, UNI
from napps.kytos.mef_eline import settings

# from napps.kytos.mef_eline.models import Circuit, Endpoint, Link


class EVC:
    """Class that represents a E-Line Virtual Connection."""

    def __init__(self, uni_a, uni_z, name, start_date=None, end_date=None,
                 bandwidth=None, primary_links=None, backup_links=None,
                 dynamic_backup_path=None):

        # Do some basic validations
        if uni_a is None or uni_z is None or name is None:
            raise TypeError("Invalid arguments")

        if ((not isinstance(uni_a, UNI)) or
                (not isinstance(uni_z, UNI))):
            raise TypeError("Invalid UNI")

        if not uni_a.is_valid() or not uni_z.is_valid():
            raise TypeError("Invalid UNI")

        self._id = uuid4().hex
        self.uni_a = uni_a
        self.uni_z = uni_z
        self.name = name
        self.start_date = start_date if start_date else now()
        self.end_date = end_date
        # Bandwidth profile
        self.bandwidth = bandwidth
        self.primary_links = primary_links
        self.backup_links = backup_links
        self.dynamic_backup_path = dynamic_backup_path
        # dict with the user original request (input)
        self._requested = None
        # circuit being used at the moment if this is an active circuit
        self.current_path = None
        # primary circuit offered to user IF one or more links were provided in
        # the request
        self.primary_path = None
        # backup circuit offered to the user IF one or more links were provided
        # in the request
        self.backup_path = None
        # datetime of user request for a EVC (or datetime when object was
        # created)
        self.request_time = now()
        # datetime when the circuit should be activated. now() || schedule()
        self.creation_time = None
        self.owner = None
        # Operational State
        self.active = False
        # Administrative State
        self.enabled = False
        # Service level provided in the request. "Gold", "Silver", ...
        self.priority = 0
        # (...) everything else from request must be @property

    # def create()
    # def discover_new_path()
    # def change_path(path)
    # def reprovision()  # force EVC (re-)provisioning
    # def remove()

    @property
    def id(self):  # pylint: disable=invalid-name
        return self._id


class Main(KytosNApp):
    """Main class of amlight/mef_eline NApp.

    This class is the entry point for this napp.
    """

    def setup(self):
        """Replace the '__init__' method for the KytosNApp subclass.

        The setup method is automatically called by the controller when your
        application is loaded.

        So, if you have any setup routine, insert it here.
        """
        pass

    def execute(self):
        """This method is executed right after the setup method execution.

        You can also use this method in loop mode if you add to the above setup
        method a line like the following example:

            self.execute_as_loop(30)  # 30-second interval.
        """
        pass

    def shutdown(self):
        """This method is executed when your napp is unloaded.

        If you have some cleanup procedure, insert it here.
        """
        pass

    # @staticmethod
    # def save_circuit(circuit):
    #     """Save a circuit to disk in the circuits path."""
    #     os.makedirs(settings.CIRCUITS_PATH, exist_ok=True)
    #     if not os.access(settings.CIRCUITS_PATH, os.W_OK):
    #         log.error("Could not save circuit on %s", settings.CIRCUITS_PATH)
    #         return False

    #     output = os.path.join(settings.CIRCUITS_PATH, circuit.id)
    #     with open(output, 'wb') as circuit_file:
    #         circuit_file.write(pickle.dumps(circuit))

    #     return True

    # @staticmethod
    # def load_circuit(circuit_id):
    #     """Load a circuit from the circuits path."""
    #     path = os.path.join(settings.CIRCUITS_PATH, circuit_id)
    #     if not os.access(path, os.R_OK):
    #         log.error("Could not load circuit from %s", path)
    #         return None

    #     with open(path, 'rb') as circuit_file:
    #         return pickle.load(circuit_file)

    # def load_circuits(self):
    #     """Load all available circuits in the circuits path."""
    #     os.makedirs(settings.CIRCUITS_PATH, exist_ok=True)
    #     return [self.load_circuit(filename) for
    #             filename in os.listdir(settings.CIRCUITS_PATH) if
    #             os.path.isfile(os.path.join(settings.CIRCUITS_PATH,
    #                                         filename))]

    # @staticmethod
    # def remove_circuit(circuit_id):
    #     """Delete a circuit from the circuits path."""
    #     path = os.path.join(settings.CIRCUITS_PATH, circuit_id)
    #     if not os.access(path, os.W_OK):
    #         log.error("Could not delete circuit from %s", path)
    #         return None

    #     os.remove(path)
    #     return True

    def send_flow_mod(self, dpid, in_port, out_port, vlan_id,
                      bidirectional=False, remove=False):
        """Send a FlowMod request to the Flow Manager."""
        if remove:
            endpoint = "%sdelete/%s" % (settings.MANAGER_URL, dpid)
            data = [{"out_port": int(out_port),
                     "match": {"in_port": int(in_port), "dl_vlan": vlan_id}}]
        else:
            endpoint = "%sflows/%s" % (settings.MANAGER_URL, dpid)
            data = [{"match": {"in_port": int(in_port), "dl_vlan": vlan_id},
                     "actions": [{"action_type": "output",
                                  "port": int(out_port)}]}]

        requests.post(endpoint, json=data)

        if bidirectional:
            self.send_flow_mod(dpid, out_port, in_port, vlan_id, remove=remove)

    def manage_circuit_flows(self, circuit, remove=False):
        """Install or remove flows that belong to the circuit."""
        vlan_id = circuit.uni_a.tag.value
        for link in circuit.path:
            if link.endpoint_a.dpid == link.endpoint_b.dpid:
                self.send_flow_mod(link.endpoint_a.dpid,
                                   link.endpoint_a.port,
                                   link.endpoint_b.port,
                                   vlan_id,
                                   bidirectional=True,
                                   remove=remove)

    # @staticmethod
    # def clean_path(path):
    #     """Return the path containing only the interfaces."""
    #     return [endpoint for endpoint in path if len(endpoint) > 23]

    # def check_link_availability(self, link):
    #     """Check if a link is available and return its total weight."""
    #     circuits = self.load_circuits()
    #     total = 0
    #     for circuit in circuits:
    #         exists = circuit.get_link(link)
    #         if exists:
    #             total += exists.bandwidth
    #         if total + link.bandwidth > 100000000000:  # 100 Gigabits
    #             return None
    #     return total

    # def check_path_availability(self, path, bandwidth):
    #     """Check if a path is available and return its total weight."""
    #     total = 0
    #     for endpoint_a, endpoint_b in zip(path[:-1], path[1:]):
    #         link = Link(Endpoint(endpoint_a[:23], endpoint_a[24:]),
    #                     Endpoint(endpoint_b[:23], endpoint_b[24:]),
    #                     bandwidth)
    #         avail = self.check_link_availability(link)
    #         if avail is None:
    #             return None
    #         total += avail
    #     return total

    @staticmethod
    def get_paths(circuit):
        """Get a valid path for the circuit from the Pathfinder."""
        endpoint = settings.PATHFINDER_URL
        request_data = {"source": circuit.uni_a.interface.id,
                        "destination": circuit.uni_z.interface.id}
        api_reply = requests.post(endpoint, json=request_data)
        if api_reply.status_code != requests.codes.ok:
            log.error("Failed to get paths at %s. Returned %s",
                      endpoint, api_reply.status_code)
            return None
        reply_data = api_reply.json()
        return reply_data.get('paths')

    def _find_interface_by_id(self, interface_id):
        """Find a Interface on controller with interface_id."""
        if interface_id is None:
            return None

        switch_id = ":".join(interface_id.split(":")[:-1])
        interface_number = int(interface_id.split(":")[-1])
        try:
            switch = self.controller.switches[switch_id]
        except KeyError:
            return None

        try:
            interface = switch.interfaces[interface_number]
        except KeyError:
            return None

        return interface

    @staticmethod
    def _get_tag_from_request(requested_tag):
        """Return a tag object from a json request.

        If there is no tag inside the request, return None
        """
        if requested_tag is None:
            return None
        try:
            return TAG(requested_tag.get("tag_type"),
                       requested_tag.get("value"))
        except AttributeError:
            return False

    def _get_uni_from_request(self, requested_uni):
        if requested_uni is None:
            return False

        interface_id = requested_uni.get("interface_id")
        interface = self._find_interface_by_id(interface_id)
        if interface is None:
            return False

        tag = self._get_tag_from_request(requested_uni.get("tag"))

        if tag is False:
            return False

        try:
            uni = UNI(interface, tag)
        except TypeError:
            return False

        return uni

    # New methods
    @rest('/v2/evc/', methods=['GET'])
    def list_circuits(self):
        pass

    @rest('/v2/evc/<circuit_id>', methods=['GET'])
    def get_circuit(self, circuit_id):
        pass

    @rest('/v2/evc/', methods=['POST'])
    def create_circuit(self):
        """Try to create a new circuit.

        Firstly, for EVPL: E-Line NApp verifies if UNI_A's requested C-VID and
        UNI_Z's requested C-VID are available from the interfaces' pools. This
        is checked when creating the UNI object.

        Then, E-Line NApp requests a primary and a backup path to the
        Pathfinder NApp using the attributes primary_links and backup_links
        submitted via REST

        # For each link composing paths in #3:
        #  - E-Line NApp requests a S-VID available from the link VLAN pool.
        #  - Using the S-VID obtained, generate abstract flow entries to be
        #    sent to FlowManager

        Push abstract flow entries to FlowManager and FlowManager pushes
        OpenFlow entries to datapaths

        E-Line NApp generates an event to notify all Kytos NApps of a new EVC
        creation

        Finnaly, notify user of the status of its request.
        """
        # Try to create the circuit object
        data = request.get_json()

        uni_a = self._get_uni_from_request(data.get('uni_a'))
        uni_z = self._get_uni_from_request(data.get('uni_z'))
        name = data.get('name')

        try:
            circuit = EVC(uni_a, uni_z, name)
        except TypeError as e:
            return jsonify("Bad request: {}".format(e)), 400

        # Request paths to Pathfinder
        circuit.primary_path = self.get_paths(circuit)[0]['hops']

        # Install the flows using FlowManager

        # Create event

        # Notify users

        return jsonify({"circuit_id": circuit.id}), 201

    # Old methods
    # @rest('/v1/circuits', methods=['GET'])
    # def get_circuits(self):
    #     """Get all the currently installed circuits."""
    #     circuits = {}
    #     for circuit in self.load_circuits():
    #         circuits[circuit.id] = circuit.as_dict()

    #     return jsonify({'circuits': circuits}), 200

    # @rest('/circuits/<circuit_id>', methods=['GET'])
    # def get_circuit(self, circuit_id):
    #     """Get a installed circuit by its ID."""
    #     circuit = self.load_circuit(circuit_id)
    #     if not circuit:
    #         return jsonify({"error": "Circuit not found"}), 404

    #     return jsonify(circuit.as_dict()), 200

    # @rest('/circuits', methods=['POST'])
    # def create_circuit(self):
    #     """Receive a user request to create a new circuit.

    #     Find a path for the circuit, install the necessary flows and store
    #     the information about it.
    #     """
    #     data = request.get_json()

    #     try:
    #         circuit = Circuit.from_dict(data)
    #     except Exception as exception:
    #         return json.dumps({'error': exception}), 400

    #     paths = self.get_paths(circuit)
    #     if not paths:
    #         error = "Pathfinder returned no path for this circuit."
    #         log.error(error)
    #         return jsonify({"error": error}), 503

    #     best_path = None
    #     # Select best path
    #     for path in paths:
    #         clean_path = self.clean_path(path['hops'])
    #         avail = self.check_path_availability(clean_path,
    #                                              circuit.bandwidth)
    #         if avail is not None:
    #             if not best_path:
    #                 best_path = {'path': clean_path, 'usage': avail}
    #             elif best_path['usage'] > avail:
    #                 best_path = {'path': clean_path, 'usage': avail}

    #     if not best_path:
    #         return jsonify({"error": "Not enought resources."}), 503

    #     # We do not need backup path, because we need to implement a more
    #     # suitable way to reconstruct paths

    #     for endpoint_a, endpoint_b in zip(best_path['path'][:-1],
    #                                       best_path['path'][1:]):
    #         link = Link(Endpoint(endpoint_a[:23], endpoint_a[24:]),
    #                     Endpoint(endpoint_b[:23], endpoint_b[24:]),
    #                     circuit.bandwidth)
    #         circuit.add_link_to_path(link)

    #     # Save circuit to disk
    #     self.save_circuit(circuit)

    #     self.manage_circuit_flows(circuit)

    #     return jsonify(circuit.as_dict()), 201

    # @rest('/circuits/<circuit_id>', methods=['DELETE'])
    # def delete_circuit(self, circuit_id):
    #     """Remove a circuit identified by its ID."""
    #     try:
    #         circuit = self.load_circuit(circuit_id)
    #         self.manage_circuit_flows(circuit, remove=True)
    #         self.remove_circuit(circuit_id)
    #     except Exception as exception:
    #         return jsonify({"error": exception}), 503

    #     return jsonify({"success": "Circuit deleted"}), 200

    # @rest('/circuits/<circuit_id>', methods=['PATCH'])
    # def update_circuit(self, circuit_id):
    #     pass

    # @rest('/circuits/byLink/<link_id>')
    # def circuits_by_link(self, link_id):
    #     pass

    # @rest('/circuits/byUNI/<dpid>/<port>')
    # def circuits_by_uni(self, dpid, port):
    #     pass
