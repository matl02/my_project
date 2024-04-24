from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types
import subprocess
import sys

class TrafficSlicing(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(TrafficSlicing, self).__init__(*args, **kwargs)
        self.emergency_mode = False  # Initial state: Common scenario

    def set_emergency_mode(self, enable):
        if enable:
            self.logger.info("Emergency scenario activated.")
            subprocess.call("./sos_scenario.sh")  # Execute script for emergency scenario
        else:
            self.logger.info("Returning to common scenario.")
            subprocess.call("./common_scenario.sh")  # Execute script for common scenario

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

    def switch_mode(self):
        if self.emergency_mode:
            self.emergency_mode = False
        else:
            self.emergency_mode = True

        self.set_emergency_mode(self.emergency_mode)  # Apply mode change

    def _handle_keyboard_input(self):
        while True:
            input_key = input("Press '1' to activate Emergency Mode, '2' to switch back to Common Mode: ")

            if input_key == '1':
                if not self.emergency_mode:
                    self.switch_mode()
            elif input_key == '2':
                if self.emergency_mode:
                    self.switch_mode()
            else:
                print("Invalid input. Press '1' for Emergency Mode or '2' for Common Mode.")

    def start_keyboard_input_thread(self):
        import threading
        input_thread = threading.Thread(target=self._handle_keyboard_input)
        input_thread.daemon = True
        input_thread.start()

    def start(self):
        super(TrafficSlicing, self).start()
        self.start_keyboard_input_thread()  # Start keyboard input listener

