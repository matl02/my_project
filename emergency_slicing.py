import argparse
import time
import subprocess
import threading
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types

class TrafficSlicing(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(TrafficSlicing, self).__init__(*args, **kwargs)
        self.emergency = 0  # Boolean that indicates the presence of an emergency scenario

        # Create a separate thread for the timer function
        self.thread = threading.Thread(target=self.timer, args=())
        self.thread.daemon = True
        self.thread.start()

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Install the table-miss flow entry.
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority, match=match, instructions=inst)
        datapath.send_msg(mod)

    def _send_packet(self, msg, datapath, in_port, actions):
        data = None
        ofproto = datapath.ofproto
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data
        out = datapath.ofproto_parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                                    in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst = eth.dst
        src = eth.src
        dpid = datapath.id

        if dpid in self.mac_to_port:
            if self.emergency == 1:  # Emergency Scenario - Create New Topology
                if dst in self.mac_to_port[dpid]:
                    out_port = self.mac_to_port[dpid][dst]
                    actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]
                    match = datapath.ofproto_parser.OFPMatch(eth_dst=dst)
                    self.add_flow(datapath, 1, match, actions)
                    self._send_packet(msg, datapath, in_port, actions)
            else:
                if dst in self.mac_to_port[dpid]:
                    out_port = self.mac_to_port[dpid][dst]
                    actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]
                    match = datapath.ofproto_parser.OFPMatch(eth_dst=dst)
                    self.add_flow(datapath, 1, match, actions)
                    self._send_packet(msg, datapath, in_port, actions)

    def timer(self):
        parser = argparse.ArgumentParser(description='Timer for switching between scenarios.')
        parser.add_argument('--normal-duration', type=int, default=60,
                            help='Duration (in seconds) for normal (non-emergency) scenario phase')
        parser.add_argument('--emergency-duration', type=int, default=60,
                            help='Duration (in seconds) for emergency scenario phase')
        args = parser.parse_args()

        while True:
            # Normal (Non-Emergency) Scenario Phase
            time.sleep(args.normal_duration)
            print('*** Emergency Scenario ***')
            subprocess.call("./sos_scenario.sh")  # Execute script for emergency scenario

            # Emergency Scenario Phase
            time.sleep(args.emergency_duration)
            print('Ending the Emergency Scenario...')
            subprocess.call("./common_scenario.sh")  # Execute script to revert to normal scenario

if __name__ == '__main__':
    pass  # RyuApp will be launched by Ryu's main process
