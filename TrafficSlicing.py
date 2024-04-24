from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types
import subprocess
from ryu.app.wsgi import ControllerBase, WSGIApplication, route  # Import for REST API

class TrafficSlicingRest(ControllerBase):  # REST API controller class
    def __init__(self, req, link, data, **config):
        super(TrafficSlicingRest, self).__init__(req, link, data, **config)
        self.ts_app = data['ts_app']  # Reference to TrafficSlicing application

    @route('ts', '/trigger_emergency', methods=['POST'])
    def trigger_emergency(self, req, **kwargs):
        self.ts_app.trigger_emergency()  # Call method to trigger emergency scenario
        return "Emergency slicing triggered\n"

class TrafficSlicing(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(TrafficSlicing, self).__init__(*args, **kwargs)
        self.rest = TrafficSlicingRest  # Initialize REST API controller

    def trigger_emergency(self):
        self.logger.info("Emergency scenario triggered by REST API command.")
        self.emergency = 1  # Set emergency flag to activate emergency scenario
        subprocess.call("./sos_scenario.sh")  # Execute script for emergency scenario
        # Additional actions to handle emergency scenario as needed

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # install the table-miss flow entry.
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # construct flow_mod message and send it.
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority, match=match, instructions=inst)
        datapath.send_msg(mod)

    def _send_packet(self, msg, datapath, out_port, actions):
        data = None
        ofproto = datapath.ofproto
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = datapath.ofproto_parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=msg.match['in_port'],
            actions=actions,
            data=data
        )
        datapath.send_msg(out)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return  # ignore LLDP packets

        dst = eth.dst
        src = eth.src

        dpid = datapath.id

        if dpid in self.mac_to_port:
            if self.emergency == 1:  # Emergency scenario logic
                if dst in self.mac_to_port[dpid]:
                    out_port = self.mac_to_port[dpid][dst]
                    actions = [parser.OFPActionOutput(out_port)]
                    match = parser.OFPMatch(eth_dst=dst)
                    self.add_flow(datapath, 1, match, actions)
                    self._send_packet(msg, datapath, out_port, actions)
            else:  # Normal scenario logic
                if dst in self.mac_to_port[dpid]:
                    out_port = self.mac_to_port[dpid][dst]
                    actions = [parser.OFPActionOutput(out_port)]
                    match = parser.OFPMatch(eth_dst=dst)
                    self.add_flow(datapath, 1, match, actions)
                    self._send_packet(msg, datapath, out_port, actions)

        # Handle additional packet processing logic as needed

    def timer(self):
        while True:
            time.sleep(60)  # Interval for toggling between normal and emergency scenarios
            self.emergency = 1
            subprocess.call("./sos_scenario.sh")  # Execute script for emergency scenario
            time.sleep(60)  # Interval for emergency scenario duration
            self.emergency = 0
